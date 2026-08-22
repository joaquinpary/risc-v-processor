# Camino crítico, skew y frecuencia de funcionamiento

> **Estado del análisis: las tres preguntas de la consigna, resueltas con
> evidencia de tres corridas reales.** Base (§2–§3): `clk` de 100 MHz de la
> Arty A7 entrando directo al pipeline, **sin** Clock Wizard — se sacó de
> `top.v` para aislar el problema. Esa corrida no cierra, y sirve para
> identificar el camino crítico y contestar la pregunta del skew con el
> caso más exigente. §4 resuelve la pregunta de la frecuencia óptima con una
> iteración real: Clock Wizard reinstalado a 62 MHz, vuelto a implementar y
> a generar bitstream — **cierra**, con margen ajustado. §7 queda la corrida
> original a 50 MHz como referencia adicional.
>
> Reportes usados: `risc-v-processor.runs/impl_1/top_timing_summary_routed.rpt`
> de cada corrida (`report_timing_summary`, diseño ruteado, Vivado 2025.1,
> `xc7a35ti-csg324-1L`) — la corrida sin Clock Wizard es de esta misma semana;
> la de 62 MHz es del 22/08/2026.

---

## 0. Las tres preguntas de la consigna

1. ¿Cuál es el camino crítico de mi sistema?
2. Ese camino crítico, ¿genera skew? ¿Qué consecuencias tiene?
3. De encontrarse skew: frecuencia óptima + métricas de Vivado + aplicarla.

La pregunta 2 tal como está escrita da a entender que el camino crítico
*causa* el skew. No es así en general — son dos fenómenos distintos que
comparten una ecuación, y conviene separarlos antes de contestar con números.

---

## 1. Dos fenómenos distintos que comparten una ecuación

### 1.1 Camino crítico — es del dato

El camino crítico es la trayectoria combinacional registro→registro con menor
margen respecto al período de reloj. Para que un path cierre en *setup*, tiene
que cumplirse:

```
T_clk  ≥  t_cq  +  t_logic,max  +  t_route,max  +  t_setup  +  t_incert  −  t_skew_útil
```

- `t_cq`: propagación clock-to-Q del flip-flop que lanza el dato.
- `t_logic,max` + `t_route,max`: la parte que uno diseña — lógica combinacional
  y el ruteo entre celdas.
- `t_setup`: tiempo de setup del flip-flop que captura.
- `t_incert`: incertidumbre de reloj (jitter + margen de la herramienta).
- `t_skew_útil`: diferencia entre cuándo llega el flanco al FF que captura y
  cuándo llegó al que lanzó. Si el reloj de captura llega *después*, ese skew
  "regala" margen de setup (por eso se llama útil).

El **camino crítico** es, por definición, el que hace mínima esa desigualdad
en todo el diseño — el que reporta el WNS (*Worst Negative Slack*, o la menor
holgura positiva si nada viola).

### 1.2 Skew — es del reloj

El skew es la diferencia en el instante de llegada del mismo flanco de reloj a
dos flip-flops distintos, producto de la red de distribución (longitud de
ruta, carga capacitiva, buffers intermedios) — no depende de qué dato viaja
por el path. En una FPGA Xilinx el reloj interno sale de un buffer global
dedicado (`BUFG`) y baja por un árbol balanceado, así que mientras el diseño
entre en una sola región de reloj (este entra: 7A35T chico, un solo dominio),
el skew típico entre dos FF cualesquiera es de decenas de picosegundos —
uno o dos órdenes de magnitud por debajo de un `t_logic` de varios ns.

### 1.3 La relación real entre ambos

No es "el camino crítico genera skew". Es al revés: **el skew es uno de los
términos que entra en la ecuación de setup (y también en la de hold) del
camino crítico**, junto con el retardo lógico y el de ruteo. Vivado separa
esto en cada path del `report_timing_summary`: reporta `Data Path Delay`
(lógica+ruteo) y `Clock Path Skew` por separado. Con eso se contesta la
pregunta 2 con evidencia en vez de intuición — ver §3.

---

## 2. El camino crítico real de este diseño (100 MHz, sin Clock Wizard)

### 2.1 Candidatos teóricos, antes de mirar el reporte

Con seis niveles de registro (ver [pipeline-depth.md](pipeline-depth.md)) y
*forwarding* activo, los combinacionales más largos que uno esperaría a
priori son la lectura del banco de registros con *write-through* combinacional
(`register.v`), los muxes de *forwarding* alimentando la ALU en EX, y —el que
termina siendo el real— el camino que junta un dato leído de memoria con la
resolución de un salto.

### 2.2 Lo que Vivado encontró (evidencia)

*Design Timing Summary*, diseño ruteado a 100 MHz (`clk` externo directo,
período 10 ns, un solo reloj — `sys_clk_pin`, sin jerarquía de Clock Wizard):

```
WNS  = -4.218 ns    TNS = -917.850 ns   (317 endpoints fallando de 5403)
WHS  = +0.080 ns    THS =    0.000 ns   (0 endpoints fallando de 5403)
WPWS = +4.500 ns    TPWS =   0.000 ns
Timing constraints are not met.
```

**No cierra.** (En esta corrida en particular no se había generado `top.bit`
todavía, pero fue porque no se corrió ese paso — no porque Vivado lo haya
bloqueado por las violaciones; el bitstream se puede generar igual, la
herramienta solo avisa.) La consecuencia concreta, antes de hablar de skew:
con WNS = −4.218 ns, a 100 MHz el diseño, tal como está, no es
funcionalmente confiable — hay 317 puntos de captura que no tienen
garantizado el dato correcto en el flanco de reloj.

El path que marca el WNS:

```
Fuente:       RAMB36E1 (u_mem, douta — lectura de memoria de datos, un load)
Destino:      u_if/pc_fetched_reg[29]/CE   (pin de clock-enable)
Data Path Delay: 13.895 ns  de 10.000 ns de período
Logic Levels:    13  (LUT3=1 LUT4=4 LUT6=7 MUXF7=1)
  lógica: 4.329 ns (31.2%)   ruteo: 9.566 ns (68.8%)
```

Recorrido, en términos funcionales (los nombres de jerarquía del reporte
ruteado no coinciden 1:1 con `top.v` porque la síntesis funde y renombra
lógica entre módulos al optimizar):

1. **Sale de la memoria de datos** (`u_mem`, salida registrada `douta`, el
   dato de un `load`).
2. Pasa por **`write_back`** (`reg_data_wb`) y reingresa al datapath como
   valor de *forwarding* hacia EX.
3. Atraviesa la **ALU** (cadena de acarreo, `MUXF7`) — es la resta que arma
   la condición de una rama.
4. Llega a la lógica de **`flush_d1`** (vaciado del pipeline) y de ahí a una
   señal de control dentro de `debug_unit`.
5. Termina en el **pin `CE`** de `pc_fetched_reg[29]`, en `instruction_fetch`
   — con **fan-out 65**: la misma señal habilita/deshabilita a la vez decenas
   de bits de ese registro.

En criollo: **el camino crítico no es "la ALU calculando", es la decisión de
salto** — un valor cargado de memoria que se reenvía a una comparación de
rama, y esa comparación tiene que llegar a tiempo para controlar el frente
del pipeline en la misma ventana de reloj. Es el path clásico de
*load-to-branch* en un pipeline con *forwarding* agresivo: el único camino
que junta memoria + *write-back* + *forwarding* + ALU + control de
stall/flush, todo en un ciclo.

---

## 3. ¿Este camino genera skew? ¿Qué consecuencias tiene?

Mirando el mismo path:

```
Clock Path Skew:  -0.082 ns   (DCD − SCD + CPR)
Clock Uncertainty: 0.035 ns   (jitter)
```

**Respuesta corta: no.** −0.082 ns de skew contra 13.895 ns de retardo de
dato es **170 veces menos** — ruido de fondo. El motivo ya está en §1.2: es
un diseño de una sola región de reloj con un único `BUFG`, así que la red de
reloj llega prácticamente pareja a origen y destino. El WNS de −4.218 ns está
gobernado casi enteramente por `t_logic + t_route` (§2.2), no por skew. El
déficit de −917.850 ns de TNS es, en la misma proporción, lógica y ruteo —
no desbalance de reloj.

### 3.1 Donde sí aparece un margen ajustado: hold, no setup

El WHS es **+0.080 ns** — mucho más ajustado que el WNS, aunque sin
violación (0 endpoints de hold fallando). El path que lo marca es de otra
familia:

```
Fuente:      u_uart_if/rx_data_40b_reg_reg[11]  (registro de recepción UART)
Destino:     entrada de datos de una BRAM (RAMB36E1)
Logic Levels: 0        — no hay lógica combinacional entre medio
Data Path Delay: 0.456 ns
Clock Path Skew: +0.079 ns
```

Patrón típico de **path corto**: el dato recibido por UART se escribe casi
directo en una memoria (coherente con cómo `debug_unit` vuelca los bytes
recibidos a la memoria de programa). Con `Logic Levels: 0`, la única lógica
disponible es el `t_cq` del registro fuente más el ruteo.

### 3.2 Por qué acá el skew y el hold parecen "lo mismo" (y no lo son)

Vale la pena aclarar esto porque los números confunden: el skew de este path
(**0.079 ns**) y el WHS resultante (**0.080 ns**) quedan casi pegados. No es
que el skew *sea* el hold — son cosas de naturaleza distinta (§1.3: skew es
un término del reloj, WHS es el margen resultante de un chequeo). Lo que pasa
es específico de este camino: al tener `Logic Levels: 0`, el presupuesto
entero del chequeo de hold se reparte entre un `t_cq` chico, un poco de
ruteo, y el skew — y el skew termina siendo el término más grande de una
cuenta que ya era chica de por sí.

Comparado con el camino de setup de §2.2, donde el skew (−0.082 ns) es 170
veces más chico que el retardo de dato (13.895 ns) y prácticamente no
participa del resultado. La regla general, útil para el informe: **el skew
pesa proporcionalmente mucho en caminos cortos (típicamente los de hold) y
casi nada en caminos largos (típicamente los de setup)** — no porque el skew
cambie de magnitud entre uno y otro (es prácticamente el mismo, ~0.08 ns en
los dos casos de esta corrida), sino porque el "colchón" de retardo de dato
que lo acompaña es radicalmente distinto.

**Consecuencia:** el hold no se arregla bajando la frecuencia — es una
restricción de tiempo *mínimo*, independiente del período de reloj. Si este
margen de 0.080 ns se diera vuelta (otra semilla de *place & route*, otro
*speed grade*, otra temperatura), la solución sería routing/skew —insertar
retardo o restringir la colocación—, nunca relajar el período.

---

## 4. Frecuencia óptima — resuelta con una iteración real: 62 MHz cierra, con margen ajustado

La estimación de primer orden desde la corrida de §2 daba
`F_max ≈ 1/(10 ns − (−4.218 ns)) ≈ 70.3 MHz`, con la advertencia de que era
optimista por venir de un solo punto lejano al objetivo (extrapolar 10× el
período real). Se reinstaló el Clock Wizard apuntando a **62 MHz**, un valor
con margen por debajo de esa cota, y se volvió a implementar y generar
bitstream.

### 4.1 Resultado

```
Período: 16.129 ns (62.000 MHz)
WNS = +0.291 ns    (0 endpoints fallando de 5403)
WHS = +0.033 ns    (0 endpoints fallando de 5403)
Timing constraints are met.
```

**Cierra** — primera de las corridas de esta serie con `top.bit` generado.
Pero el margen es chico en las dos puntas:

- El camino crítico de setup usa **15.283 ns de los 16.129 ns** de período
  disponibles (94.8%) — el WNS de 0.291 ns es apenas el 1.8% del período.
- El WHS de **0.033 ns** es el más ajustado de las tres corridas hechas
  hasta ahora (0.079 ns a 50 MHz, 0.080 ns a 100 MHz, 0.033 ns acá). El hold
  en teoría no depende de la frecuencia, pero cada corrida de *place & route*
  encuentra una solución de ruteo distinta, y en ésta el margen quedó más
  fino que en las otras dos.

El path crítico es, otra vez, la misma familia que en §2 y en §7: memoria de
datos → `write_back`/*forwarding* → ALU → `flush_d1`, esta vez terminando en
el pin `CE` de `instr_skid_reg[0]` (antes había sido `R` de `pc_id_reg` a
50 MHz, `CE` de `pc_fetched_reg` a 100 MHz). Tercera confirmación de que el
cuello de botella real de este diseño es la cadena
*memoria→forwarding→ALU→control de stall/flush*, no la ALU aislada — cambia
qué registro de control específico "pierde" según cómo resuelva el
*placement* en cada corrida, pero es siempre la misma cadena funcional.

El skew en este path sigue siendo insignificante: `Clock Path Skew: -0.016ns`
contra 15.283 ns de retardo de dato — la teoría se sostiene en las tres
frecuencias probadas (§3).

### 4.2 ¿62 MHz es la frecuencia a usar?

Cierra, pero con poco colchón para variación de proceso/temperatura/tensión
— en particular el margen de hold (0.033 ns), que es justo el tipo de
violación que no se arregla después bajando el reloj (§3.2). Dos caminos
razonables desde acá:

- **Aceptar 62 MHz documentando el margen ajustado** — válido si el objetivo
  del TP es mostrar el método de análisis, no maximizar la frecuencia.
- **Retroceder unos MHz (58–60) y volver a implementar** para confirmar que
  el margen mejora en las dos restricciones antes de programar la placa de
  verdad. Es la opción más prudente si el bitstream se va a usar en hardware
  real y no sólo como ejercicio de timing closure.

Si se elige una frecuencia final, falta **actualizar el parámetro `FREQ` de
`top.v`** (usado por `uart_interface` para el generador de baudrate) junto
con el nuevo `clk_out1`, para que el baudrate de la UART no se corra.

---

## 5. Nota de método: por qué conviene medir en vez de asumir

Del `Data Path Delay` del camino crítico (13.895 ns), el **68.8% es ruteo y
solo 31.2% es lógica**. En FPGA el retardo de interconexión domina sobre el
de las compuertas — al revés de la intuición de diseño lógico "de libro"
donde se cuentan niveles de lógica y ya. La ubicación física (dónde cae cada
registro después de *place & route*) pesa tanto o más que la profundidad
lógica, y eso solo lo dice la herramienta después de rutear — no se puede
adivinar leyendo el RTL.

---

## 6. Cómo se explica en el informe

> Con el reloj de 100 MHz de la placa entrando directo al pipeline (sin
> divisor), el análisis estático de temporización (STA) sobre el diseño
> ruteado muestra que el sistema no cierra: WNS = −4.218 ns, con 317 de 5403
> puntos de captura fallando. El camino crítico no corresponde a la ejecución
> de una ALU aislada sino a la cadena *load-to-branch*: un dato leído de
> memoria de datos se reenvía por *forwarding* hasta la comparación de una
> rama, y la señal de control que esa comparación produce debe alcanzar, en
> la misma ventana de reloj, el pin de clock-enable de los registros del
> latch IF/ID (fan-out 65).
>
> El skew de la red de reloj en ese camino es de −0.082 ns, 170 veces menor
> que el retardo de datos (13.895 ns): en un diseño de una sola región de
> reloj distribuida por un `BUFG` único, el skew no es el factor limitante de
> la frecuencia máxima — el déficit de timing es enteramente lógica y ruteo.
> El margen más ajustado del diseño (WHS = 0.080 ns) tampoco aparece en el
> camino crítico de *setup* sino en un camino corto de *hold* (UART hacia una
> BRAM, sin lógica intermedia), donde el skew sí pesa proporcionalmente —no
> porque cambie de magnitud, sino porque ahí no hay retardo de dato que lo
> diluya. Consistente con la teoría, esa restricción de hold es independiente
> del período de reloj y no se resuelve bajando la frecuencia de operación.
>
> A partir de la estimación de primer orden (≈70.3 MHz) se reinstaló el
> Clock Wizard apuntando a 62 MHz y se volvió a implementar: la corrida
> cierra (WNS = +0.291 ns, WHS = +0.033 ns, timing constraints met), con el
> mismo camino crítico funcional que en las corridas anteriores —memoria de
> datos reenviada por *forwarding* hasta la ALU y de ahí al control de
> vaciado del pipeline— cambiando sólo qué registro de control puntual
> termina siendo el más ajustado. El margen es chico en ambas restricciones,
> en particular en hold, por lo que 62 MHz queda como frecuencia candidata
> más que como valor final: cierra, pero con poco colchón para variación de
> proceso/temperatura/tensión.

---

## 7. Anexo — las tres corridas, lado a lado

Antes de sacar el Clock Wizard, el diseño se había implementado a 50 MHz
(período 20 ns, `clk` de 100 MHz → MMCM → `BUFG` → `clk_out1_clock_wizard_1`
de 50 MHz). Esa corrida cerraba cómodo. Con las tres corridas hechas hasta
ahora (50 MHz con CW → 100 MHz sin CW → 62 MHz con CW reinstalado) queda la
serie completa:

```
                    50 MHz (CW)     100 MHz (sin CW)   62 MHz (CW)
Período             20.000 ns        10.000 ns          16.129 ns
WNS                 +2.616 ns        −4.218 ns  ←viola   +0.291 ns
TNS                  0.000 ns      −917.850 ns            0.000 ns
Endpoints fallando   0 / 5403        317 / 5403           0 / 5403
WHS                 +0.079 ns        +0.080 ns           +0.033 ns  ←el más ajustado
Data delay crítico  16.702 ns        13.895 ns           15.283 ns
% del período usado    83.5%           139% (viola)         94.8%
Skew en ese path    −0.076 ns        −0.082 ns           −0.016 ns
Destino del WNS     R pc_id_reg      CE pc_fetched_reg    CE instr_skid_reg
top.bit generado         sí               no (no se corrió)      sí
```

Tres cosas se sostienen en las tres corridas, y es lo que vale la pena citar
en el informe como conclusión general (no depende de a qué frecuencia se
mire):

1. **El camino crítico es siempre la misma cadena funcional** —memoria de
   datos → *write-back* → *forwarding* → ALU → control de stall/flush— y
   sólo cambia qué registro de control puntual (`pc_id`, `pc_fetched`,
   `instr_skid`) termina siendo el más ajustado según cómo resuelva el
   *placement* esa corrida en particular.
2. **El skew nunca es el factor limitante**: se mantiene en el orden de
   pocas centésimas de ns en las tres corridas, dos órdenes de magnitud por
   debajo del retardo de dato del camino crítico.
3. **Extrapolar F_max desde un solo punto no es confiable**: la estimación
   desde 50 MHz daba ≈57.5 MHz, la estimación desde 100 MHz daba ≈70.3 MHz, y
   el valor real (probado, no extrapolado) quedó en 62 MHz cerrando con poco
   margen — ninguna de las dos extrapolaciones acertó, aunque la de 100 MHz
   (más cercana al punto real) quedó más cerca que la de 50 MHz. Confirma que
   hace falta iterar con corridas reales, no alcanza con una cuenta.

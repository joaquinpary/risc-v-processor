# Informe: timing del sistema y carga de programa

> Documento de síntesis para el informe final del TP. Reúne, en formato de
> informe y sin fragmentos de código, los dos puntos de la consigna ya
> resueltos con evidencia real: la sección **Clock** (camino crítico, skew,
> frecuencia de funcionamiento) y la sección **Carga de Programa**. El
> detalle técnico completo —con los reportes de Vivado y el RTL citado línea
> por línea— queda en `docs/clock-timing.md` y `docs/program-loading.md`;
> este documento es la versión narrativa, pensada para copiarse casi tal
> cual al informe.

---

## 1. Timing del sistema

### 1.1 Qué pide la consigna

Al llegar la etapa de integración, la consigna pide identificar el camino
crítico del sistema, determinar si ese camino genera skew y qué
consecuencias tiene, y —de encontrarse skew— hallar la frecuencia de
funcionamiento óptima, generar métricas con las herramientas de Vivado y
aplicar esa frecuencia al diseño.

La pregunta, tal como está formulada, sugiere una relación de causa y efecto
entre el camino crítico y el skew que no es correcta en términos generales.
Antes de responder con números conviene separar los dos conceptos.

### 1.2 Marco teórico: camino crítico y skew son fenómenos distintos

El **camino crítico** es la trayectoria combinacional entre dos registros
con menor margen respecto del período de reloj. Para que ese camino cumpla
la restricción de *setup*, el período de reloj tiene que ser mayor o igual a
la suma de la propagación de salida del registro que lanza el dato, el
retardo de la lógica combinacional y del ruteo que atraviesa, el tiempo de
setup del registro que captura, la incertidumbre de reloj (jitter y margen
de herramienta) y, restando, el skew útil que pudiera existir a favor. El
camino crítico es, por definición, el que hace mínimo ese margen en todo el
diseño; en las herramientas de Xilinx ese margen mínimo se reporta como WNS
(*Worst Negative Slack*).

El **skew**, en cambio, es la diferencia en el instante de llegada del mismo
flanco de reloj a dos flip-flops distintos, producto de la red de
distribución de reloj —no depende de qué dato viaja por el camino de datos.
En una FPGA Xilinx el reloj interno se distribuye por un buffer global
dedicado y un árbol balanceado, de modo que, mientras el diseño quede dentro
de una sola región de reloj (como es el caso de este proyecto, que entra
cómodo en un dispositivo 7A35T), el skew típico entre dos registros
cualesquiera es del orden de centésimas de nanosegundo, uno o dos órdenes de
magnitud por debajo de un retardo lógico típico de varios nanosegundos.

La relación real entre ambos no es que el camino crítico genere skew, sino
que el skew es uno de los términos que entra en la ecuación de setup (y
también en la de *hold*) del camino crítico, junto con el retardo lógico y
de ruteo. Las herramientas de análisis estático de temporización (STA) de
Vivado reportan esos dos términos por separado en cada camino, lo que
permite contestar con evidencia, en vez de intuición, si el skew es o no el
factor limitante en este diseño particular.

### 1.3 Metodología

El análisis se hizo sobre el diseño ya ruteado (post *place & route*),
usando el reporte de resumen de temporización de Vivado, que para cada
camino de reloj informa el margen de *setup* (WNS) y de *hold* (WHS) del
peor caso, además del detalle del camino que produce cada uno de esos
valores: cuánto retardo aporta la lógica, cuánto el ruteo, y cuánto el skew
de la red de reloj.

Se compararon tres implementaciones del mismo diseño, sin cambiar una sola
línea del datapath, variando únicamente la fuente de reloj:

1. El reloj de 50 MHz que entrega el generador de reloj (*Clock Wizard*) a
   partir del oscilador de 100 MHz de la placa, que era la configuración
   original del proyecto.
2. El reloj de 100 MHz del oscilador entrando directo al pipeline, sin
   generador de reloj de por medio —un experimento deliberado para forzar
   el sistema a un extremo y aislar con claridad el camino crítico y el
   comportamiento del skew.
3. El reloj de 62 MHz, resultado de reinstalar el generador de reloj
   apuntando a un valor intermedio, elegido a partir de la estimación
   obtenida en el paso anterior.

### 1.4 Resultados

| Frecuencia | Margen de *setup* (WNS) | Margen de *hold* (WHS) | Cierra la temporización |
|---|---|---|---|
| 50 MHz (con generador de reloj) | +2,62 ns | +0,079 ns | Sí, con margen amplio |
| 100 MHz (reloj directo, sin generador) | −4,22 ns | +0,080 ns | No — 317 de 5403 puntos de captura violados |
| 62 MHz (generador reinstalado) | +0,29 ns | +0,033 ns | Sí, con margen ajustado |

El resultado más claro es el de 100 MHz: al duplicar la frecuencia respecto
de la configuración original, el margen de *setup* pasa de ampliamente
positivo a claramente negativo, y el diseño deja de cumplir la
temporización en más de trescientos puntos de captura. El margen de *hold*,
en cambio, prácticamente no se mueve entre las tres corridas —una firma
inequívoca de que el problema es de *setup* puro, y confirma que el *hold*
no depende del período de reloj, tal como predice la teoría.

### 1.5 El camino crítico real del sistema

En las tres corridas, el camino que determina el margen de *setup* resultó
ser siempre la misma cadena funcional, más allá de que la implementación
concreta cambie de una corrida a otra: un dato leído de la memoria de datos
se reenvía por adelantamiento (*forwarding*) hasta la unidad aritmética, que
lo usa para resolver la condición de un salto; la señal de control que
produce esa resolución tiene que llegar, en la misma ventana de reloj, a los
registros que gobiernan el vaciado del frente del pipeline.

Es un resultado que vale la pena remarcar porque no es el que uno esperaría
a priori. La intuición de libro señala a la unidad aritmética operando de
manera aislada, o a la lectura del banco de registros, como los candidatos
más probables al camino más largo. Lo que muestra el análisis es que el
cuello de botella real de este diseño es la cadena completa que une la
memoria de datos, el camino de escritura de resultados, el adelantamiento de
operandos, la unidad aritmética y la lógica de control de vaciado del
pipeline — el camino clásico de "carga seguida de salto" (*load-to-branch*)
en un pipeline con adelantamiento agresivo. En las tres corridas, cambia
exactamente qué registro de control puntual del frente del pipeline termina
siendo el más ajustado (según cómo resuelva la ubicación física la
herramienta en cada corrida en particular), pero la cadena funcional que lo
alimenta es siempre la misma.

Una observación adicional, útil para entender por qué el camino crítico no
se puede adivinar leyendo el código fuente: del retardo total del camino
crítico, la mayor parte corresponde al ruteo entre celdas y no a la lógica
en sí —una proporción cercana a dos tercios de ruteo contra un tercio de
lógica, consistente en las tres corridas. En un diseño sobre FPGA el retardo
de interconexión domina sobre el de las compuertas, al revés de la
intuición de diseño lógico de libro donde alcanza con contar niveles de
lógica. La ubicación física de cada registro después de la etapa de
posicionamiento y ruteo pesa tanto o más que la profundidad lógica, y eso
solo lo revela la herramienta después de haber ruteado el diseño completo.

### 1.6 El skew no es el factor limitante

En las tres corridas, el skew de la red de reloj sobre el camino crítico se
mantuvo en el orden de unas pocas centésimas de nanosegundo, dos órdenes de
magnitud por debajo del retardo de datos de ese mismo camino. La respuesta a
la pregunta de la consigna es, entonces, que el camino crítico de este
sistema no genera un skew relevante, y que el déficit de temporización
observado a 100 MHz es enteramente atribuible a retardo de lógica y de
ruteo, no a un desbalance de la red de reloj. Es una consecuencia esperable
del tipo de diseño: al tratarse de un sistema que entra cómodo en una única
región de reloj de la FPGA, distribuida por un único buffer global, la red
de reloj llega de manera prácticamente pareja a cualquier par de registros
del diseño.

El margen más ajustado de las tres corridas no aparece, en ningún caso, en
el camino crítico de *setup*, sino en un camino de *hold* completamente
distinto: el que conecta el receptor de la interfaz UART con la memoria de
programa, un camino sin lógica combinacional entre los dos registros
involucrados. Ahí sí el skew pesa proporcionalmente mucho más que en el
camino de *setup*, no porque cambie de magnitud —es prácticamente el mismo
valor en términos absolutos—, sino porque en un camino tan corto no hay
retardo de datos que lo diluya: el presupuesto entero del margen de *hold*
se reparte entre la propagación del registro fuente, un poco de ruteo, y el
skew. La consecuencia para el diseño es que esa restricción de *hold* es
independiente de la frecuencia de reloj elegida y no se puede corregir
bajando la velocidad de operación: de encontrarse en algún momento una
violación ahí, la solución pasaría por restringir la ubicación física de
esos registros o insertar retardo adicional en el camino, nunca por relajar
el período.

### 1.7 Determinación de la frecuencia de funcionamiento

A partir del margen negativo obtenido a 100 MHz se calculó una primera
estimación de la frecuencia máxima teórica, dividiendo la unidad por la
diferencia entre el período usado y el margen medido. Esa estimación dio un
valor cercano a los 70 MHz. Sin embargo, la misma cuenta aplicada a la
corrida original de 50 MHz arroja una estimación distinta, cercana a los 57
MHz —las dos estimaciones no coinciden entre sí, lo cual demuestra que
extrapolar la frecuencia máxima a partir de un único punto lejano al
objetivo no es un método confiable: el camino crítico que resulta más
ajustado cambia según cómo la herramienta resuelve la ubicación física bajo
cada restricción de período, de modo que el margen medido a una frecuencia
no se traslada linealmente a otra.

Por esa razón se optó por un método iterativo: se reinstaló el generador de
reloj apuntando a un valor intermedio, con margen por debajo de la
estimación optimista, y se volvió a implementar el diseño completo. El
resultado, a 62 MHz, cierra la temporización con todos los puntos de
captura satisfechos, tanto en *setup* como en *hold*, pero con un margen
notablemente más ajustado que el de la configuración original a 50 MHz: el
camino crítico de *setup* llega a usar prácticamente la totalidad del
período disponible, y el margen de *hold* resultó el más chico de las tres
corridas realizadas.

Esa estrechez de margen es un dato relevante para la decisión final de
frecuencia de operación. Un margen tan ajustado deja poco colchón frente a
la variación de proceso de fabricación, temperatura y tensión de
alimentación que cualquier implementación real debe tolerar, y frente a la
variabilidad que introduce la propia herramienta de posicionamiento y ruteo
entre una corrida y otra. En consecuencia, 62 MHz queda documentado como
frecuencia candidata, validada empíricamente como alcanzable, más que como
el valor final recomendado para operar la placa: para un uso en hardware
real conviene retroceder unos pocos megahertz adicionales y confirmar, con
una nueva implementación, que el margen mejora de manera cómoda en las dos
restricciones antes de dar la frecuencia por definitiva.

### 1.8 Conclusiones de la sección

El camino crítico de este procesador no es la unidad aritmética operando de
manera aislada, sino la cadena que une una lectura de memoria, el
adelantamiento de datos, la resolución de un salto y el control de vaciado
del pipeline —un resultado consistente en las tres frecuencias evaluadas. El
skew de la red de reloj no resultó, en ningún caso, un factor limitante de
la frecuencia de operación: el déficit de temporización observado en la
configuración más exigente es enteramente atribuible a retardo de lógica y
de ruteo. La frecuencia máxima de operación no se puede estimar de manera
confiable con una sola corrida: hizo falta iterar con implementaciones
reales para encontrar un punto de cierre, y el valor encontrado (62 MHz)
cierra con un margen lo bastante ajustado como para tratarlo como punto de
partida de un ajuste fino, y no como frecuencia final de la placa.

---

## 2. Carga de programa

### 2.1 Qué pide la consigna

El programa que corre en el procesador debe estar escrito en ensamblador,
contar con un mecanismo que lo traduzca a lenguaje máquina, e incluir una
instrucción de detención. El sistema, por su parte, debe permitir programar
la memoria de programa por software y reprogramar el procesador de manera
dinámica, sin volver a sintetizar el diseño, comunicándose exclusivamente
por UART. Sobre ese mecanismo, la consigna pide responder si es necesario
vaciar la memoria de datos, los registros, el pipeline y la memoria de
programa cada vez que se carga un programa nuevo.

Todos estos puntos ya están resueltos en el proyecto: existe un traductor de
ensamblador a lenguaje máquina, un protocolo de comunicación por UART que
permite programar y reprogramar el procesador sin tocar el bitstream, y una
convención de diseño para la instrucción de detención. Lo que sigue es la
explicación de cómo funciona ese mecanismo y, para cada una de las cuatro
preguntas, la razón concreta detrás de cada respuesta.

### 2.2 El mecanismo de carga

La comunicación entre la computadora y la placa se realiza mediante un
protocolo propio sobre UART, en el que cada mensaje —en cualquiera de los
dos sentidos— ocupa un tamaño fijo: un byte de comando seguido de cuatro
bytes de dato. Del lado de la placa, una unidad de depuración recibe esos
mensajes y actúa como intermediaria entre la computadora y el procesador:
puede pausarlo, hacerlo avanzar un ciclo de reloj a la vez, dejarlo correr
libremente hasta que termine el programa, escribir instrucciones nuevas en
la memoria de programa, y leer el contenido de los registros, de la memoria
de datos, del contador de programa y de los registros intermedios entre
etapas del pipeline.

Cargar un programa nuevo consiste en tres pasos encadenados: primero se
envía un comando de reinicio, que además de reiniciar el procesador rebobina
el puntero interno que indica en qué dirección de la memoria de programa se
va a escribir la próxima instrucción; después se envía una instrucción por
mensaje, cada una escrita en la dirección que indica ese puntero, que se
incrementa automáticamente después de cada escritura; y finalmente se envía
un segundo comando de reinicio, que deja el contador de programa en cero y
el procesador listo para correr el programa recién cargado. El primer
reinicio no es opcional: como el protocolo no incluye la dirección de
memoria en cada mensaje de carga —solo el contenido de la instrucción—, sin
ese primer paso la carga seguiría escribiendo a partir de donde había
quedado el puntero de la carga anterior, en vez de empezar desde el
principio de la memoria de programa.

Todo este intercambio ocurre con el diseño ya configurado en la FPGA, sin
generar un bitstream nuevo ni volver a sintetizar: es tráfico normal sobre
los puertos de escritura y lectura que ya forman parte del diseño. Con esto
queda satisfecho el requisito de la consigna de reprogramar el procesador de
manera dinámica y exclusivamente por UART.

### 2.3 Las cuatro preguntas de la consigna

**¿Es necesario vaciar la memoria de datos?** No, y el propio diseño no lo
permite: la memoria de datos está implementada sobre un bloque de memoria
dedicado de la FPGA, un recurso que no cuenta con una entrada de borrado
masivo —solo se puede escribir posición por posición— y el puerto por el que
la unidad de depuración accede a ella desde afuera del procesador está
cableado únicamente para lectura. En la práctica, esto significa que si se
reprograma el procesador sin volver a configurar la placa desde cero, la
memoria de datos conserva lo que haya dejado la ejecución del programa
anterior. Un programa que necesite arrancar con la memoria de datos en
cero tiene que inicializar explícitamente las posiciones que va a usar, en
lugar de asumir que ya están limpias.

**¿Y los registros?** Sí, y de manera automática. El banco de registros sí
cuenta con lógica de reinicio completo, que se dispara con el mismo pulso
que genera el comando de reinicio del protocolo de carga. Como la secuencia
de carga de un programa incluye ese comando tanto al principio como al
final, los treinta y dos registros quedan en cero en cada carga sin que haga
falta pedirlo aparte. Es una diferencia importante respecto de la memoria de
datos: mientras que un programa razonable puede convivir con memoria de
datos sucia si inicializa lo que necesita, prácticamente cualquier programa
de prueba asume que los registros arrancan en cero.

**¿Se necesita vaciar el pipeline?** Sí, y también ocurre de manera
automática con el mismo pulso de reinicio. Todos los registros intermedios
entre etapas del pipeline —los que retienen la instrucción, sus operandos y
las señales de control mientras viaja de una etapa a la siguiente— se
limpian por completo cuando se recibe el comando de reinicio, junto con el
contador de programa. Es un paso imprescindible: sin este vaciado, una
instrucción del programa anterior podría seguir circulando por el pipeline
en el momento en que empieza a escribirse el programa nuevo, y terminar
teniendo un efecto sobre registros o memoria que ya no corresponde a nada
que el programa nuevo esperaría.

**¿Y la memoria de programa?** Tampoco se vacía, por la misma razón que la
memoria de datos: es otro bloque de memoria dedicado sin entrada de borrado
masivo, y el comando de reinicio solo rebobina el puntero de escritura, no
el contenido. Esto tiene una consecuencia concreta que vale la pena señalar:
si se carga un programa más corto después de haber cargado uno más largo,
las direcciones que el programa nuevo no llega a reescribir conservan las
instrucciones del programa anterior, y el procesador las va a ejecutar si el
flujo de control llega hasta ahí. La solución adoptada en este proyecto no
es una garantía automática del sistema, sino una convención del lado del
software: todos los programas de prueba se rellenan hasta ocupar la misma
cantidad fija de palabras, de modo que cargar cualquiera de ellos sobre
cualquier otro siempre reescribe exactamente el mismo rango de direcciones y
nunca deja un resto del programa anterior. Es una disciplina a mantener
mientras se preparen programas nuevos para la demostración, no una
propiedad garantizada por el hardware.

### 2.4 La instrucción de detención

El conjunto de instrucciones implementado no incluye un código de operación
dedicado a detener el procesador. En su lugar, se usa como marca de fin de
programa una palabra de memoria completamente en cero, que no corresponde a
ninguna instrucción válida del set implementado. El procesador detecta esa
marca en la etapa de decodificación y, al encontrarla, deja de avanzar. Dos
recaudos evitan que esta detección se dispare por error: se ignora durante
los primeros ciclos posteriores a un reinicio, mientras el pipeline todavía
se está llenando, y se distingue de las burbujas que produce un salto
tomado, que también dejan esa etapa en cero pero no significan el fin del
programa.

Como la memoria de programa arranca en cero al configurar la FPGA por
primera vez y no cuenta con archivo de inicialización propio, cualquier
dirección más allá de la última instrucción realmente cargada actúa, por
defecto, como marca de fin de programa —a menos que ahí haya quedado
contenido de una carga anterior, que es exactamente el riesgo señalado en la
pregunta sobre la memoria de programa. Si el flujo de ejecución nunca llega
a una palabra en cero, ya sea porque un salto la esquiva o porque en esa
zona quedó contenido no nulo de una carga previa, el procesador no se
detiene solo: en el modo de ejecución continua queda corriendo de manera
indefinida, y como en ese modo la unidad de depuración deja de atender la
UART hasta que el procesador se detiene, la comunicación con la placa queda
sin respuesta hasta un reinicio físico o una nueva programación. En el modo
paso a paso esta situación no es un problema equivalente, porque cada paso
se confirma de manera individual sin depender de que el programa llegue a
su fin.

### 2.5 Conclusiones de la sección

De las cuatro preguntas de la consigna, dos se responden de manera
afirmativa y dos de manera negativa, y en los cuatro casos la respuesta se
deriva directamente de qué recursos de la FPGA cuentan o no con una entrada
de borrado masivo. Los registros y el pipeline se vacían de manera
automática en cada carga porque están construidos con biestables que sí
tienen lógica de reinicio explícita, alcanzados por el mismo pulso que
genera el protocolo. La memoria de datos y la memoria de programa no se
vacían, porque ambas están implementadas sobre bloques de memoria dedicados
de la FPGA que solo admiten escritura posición por posición. Para la memoria
de programa, esa limitación tiene una consecuencia práctica concreta —el
riesgo de dejar instrucciones residuales de una carga anterior—, resuelta en
este proyecto mediante una convención del lado del software y no mediante
una garantía del hardware. La instrucción de detención que pide la consigna,
finalmente, tampoco es un código de operación real, sino una convención
similar: una palabra en cero que no decodifica a ninguna instrucción válida,
usada como marca de fin de programa y detectada por hardware en la etapa de
decodificación.

---

## 3. Síntesis general

Los dos puntos analizados en este informe comparten un mismo patrón de
trabajo: en ambos casos, la consigna plantea preguntas que a primera vista
admiten una respuesta intuitiva —el camino crítico "debería" ser la unidad
aritmética, la memoria "debería" vaciarse al reprogramar—, y en los dos
casos la respuesta correcta surgió de revisar la implementación real en
lugar de asumir el comportamiento esperado de un diseño de libro. El camino
crítico resultó ser la cadena de adelantamiento hacia la resolución de
saltos, no la unidad aritmética aislada, y solo la evidencia de los reportes
de temporización lo mostró con claridad. La posibilidad de vaciar cada
recurso de memoria durante una reprogramación depende, en última instancia,
de si ese recurso está implementado con biestables o con bloques de memoria
dedicados de la FPGA, y esa distinción no es evidente si no se revisa cómo
está conectada cada señal de reinicio en el diseño.

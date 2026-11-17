# La IA solo propone señales con evidencia; todo lo demás sale de reglas y catálogo

El Lector con IA devuelve únicamente **señales** de un catálogo cerrado, la ubicación dicha, un tipo de
incidente sugerido y pre-marcas. Cada una viene con su **evidencia** textual, y lo que no tiene
evidencia en el relato se descarta. La **prioridad**, la **próxima pregunta**, las **instrucciones**
y el texto de la **Carta** los producen reglas y un catálogo curado a mano, nunca el modelo.
Lo decidimos así porque, en una sala de emergencias, una instrucción o una prioridad inventada es un
riesgo directo para una persona. Además, el AI Act europeo trata la clasificación de llamadas de
emergencia como de alto riesgo, y el enunciado evalúa explícitamente el control de alucinaciones.

## Considered Options

- **Que el LLM devuelva la Carta completa** (prioridad, instrucciones y resumen), como hacen algunos
  productos del mercado. Es más simple y redacta mejor, pero no se puede auditar y un error llega
  directo al ciudadano.
- **Solo reglas, sin LLM.** Es determinista, pero se le escapan el lunfardo y las formas raras de decir
  las cosas, y no cumple con el modo real que pide el enunciado.

## Consequences

- El modo simulado (`LLM_PROVIDER=mock`) es un producto completo: el lector por reglas alimenta el
  mismo motor de decisión que la IA.
- El valor de la IA se mide como **cuántas preguntas clave pre-marca bien**, no como "calidad del
  texto".
- Que la IA redacte el resumen de la Carta queda como mejora futura y requeriría revisar este ADR.

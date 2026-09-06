# Salida anticipada presupuestada para políticas robóticas

## 1. Introducción

Una política robótica construida sobre un modelo multimodal de gran tamaño
dedica la misma cantidad de cómputo a cada paso, tanto si la pinza atraviesa un
espacio vacío como si se cierra sobre una manija. Este trabajo se pregunta si
dicha política puede decidir, en cada paso, qué parte de su propia red ejecutar.

### 1.1 Contribuciones

- Una regla de salida que interpreta la concordancia entre dos predicciones internas adyacentes.
- Un asignador de presupuesto que reparte el cómputo sobrante entre los pasos restantes.

## 2. Método

Sea $o_t$ la observación en el paso $t$ y $\pi_\theta$ la política. El objetivo
de entrenamiento es la habitual pérdida de clonación de comportamiento sobre un
conjunto de demostraciones $\mathcal{D}$:

$$\mathcal{L}(\theta) = \mathbb{E}_{(o,a) \sim \mathcal{D}}
\left[ -\log \pi_\theta(a \mid o) \right]$$

## 3. Experimentos

| Método | Éxito | Latencia | Parámetros |
| --- | --- | --- | --- |
| Modelo completo | 74.8% | 240 ms | 7B |
| Salida voraz | 72.0% | 104 ms | 7B |
| Salida presupuestada (nuestra) | 74.3% | 88 ms | 7B |

![](images/fig1.png)

Tasa de éxito frente al cómputo medio empleado por paso.

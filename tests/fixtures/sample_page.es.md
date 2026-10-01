# Salida anticipada presupuestada para políticas robóticas

## 3. Método

### 3.1 Regla de salida

Las salidas anticipadas se estudian desde BranchyNet (Teerapittayanon et al., 2016),
donde un umbral de confianza en una capa intermedia decide si conviene detenerse.
Una política no dispone de esa confianza, de modo que comparamos las acciones que
predicen dos salidas contiguas y nos detenemos en cuanto coinciden.

Sea $o_t$ la observación en el paso $t$ y $a^{(k)}_t$ la acción predicha en la
salida $k$. La política sale en el primer $k$ que cumple

$$\lVert a^{(k)}_t - a^{(k-1)}_t \rVert_2 < \alpha$$

con $\alpha = 0.15$ en todos los casos. La regla no necesita una red propia: ambas
acciones ya se calculan al recorrer la red troncal
(Vaswani et al., 2017).

## 4. Experimentos

| Método | Éxito | Latencia | GFLOPs | Parámetros |
| --- | --- | --- | --- | --- |
| Modelo completo (Brohan et al., 2023) | 74.8% | 240 ms | 31.2 | 7B |
| Media profundidad fija | 68.1% | 121 ms | 15.6 | 7B |
| Salida voraz | 72.0% | 104 ms | 11.4 | 7B |
| Salida presupuestada (nuestra) | 74.3% | 88 ms | 9.7 | 7B |

![](images/fig1.png)

Tasa de éxito frente al cómputo medio empleado por paso.

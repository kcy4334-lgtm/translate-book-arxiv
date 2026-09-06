# Budgetierter Frühausstieg für Roboter-Policies

## 3. Methode

### 3.1 Ausstiegsregel

Vorzeitige Ausstiege werden seit BranchyNet (Teerapittayanon et al., 2016)
untersucht, wo eine Konfidenzschwelle in einer Zwischenschicht den Abbruch
auslöst. Da Policies diese Konfidenz fehlt, vergleichen wir zwei benachbarte
Ausstiege und brechen bei übereinstimmenden Aktionen ab.

Sei $o_t$ die Beobachtung in Schritt $t$, $a^{(k)}_t$ die an Ausstieg $k$
vorhergesagte Aktion. Die Policy steigt beim ersten $k$ aus, für das gilt:

$$\lVert a^{(k)}_t - a^{(k-1)}_t \rVert_2 < \alpha$$

mit durchgängig $\alpha = 0.15$. Die Regel braucht kein eigenes Netz; beide
Aktionen fallen im Backbone-Durchlauf ohnehin an (Vaswani et al., 2017).

## 4. Experimente

| Verfahren | Erfolg | Latenz | GFLOPs | Parameter |
| --- | --- | --- | --- | --- |
| Vollständiges Modell (Brohan et al., 2023) | 74.8% | 240 ms | 31.2 | 7B |
| Feste halbe Tiefe | 68.1% | 121 ms | 15.6 | 7B |
| Gieriger Ausstieg | 72.0% | 104 ms | 11.4 | 7B |
| Budgetierter Ausstieg (unser Verfahren) | 74.3% | 88 ms | 9.7 | 7B |

![](images/fig1.png)

Erfolgsquote über dem mittleren Rechenaufwand pro Schritt.

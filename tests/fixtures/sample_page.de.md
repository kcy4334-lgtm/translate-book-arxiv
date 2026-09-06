# Budgetierter vorzeitiger Ausstieg für Roboter-Policies

## 1. Einleitung

Eine Roboter-Policy, die auf einem großen multimodalen Modell aufbaut, wendet in
jedem Schritt denselben Rechenaufwand auf, gleichgültig ob der Greifer leeren
Raum durchquert oder sich um einen Griff schließt. Die vorliegende Arbeit geht
der Frage nach, ob sie in jedem Schritt selbst entscheiden kann, welchen Anteil
ihres eigenen Netzes sie ausführt.

### 1.1 Beiträge

- Eine Ausstiegsregel, die die Übereinstimmung zwischen zwei benachbarten internen Vorhersagen ausliest.
- Ein Budgetzuteiler, der das Verbleibende auf die noch ausstehenden Schritte verteilt.

## 2. Methode

Sei $o_t$ die Beobachtung im Schritt $t$ und $\pi_\theta$ die Policy. Das
Trainingsziel ist der übliche Behaviour-Cloning-Verlust über einer
Demonstrationsmenge $\mathcal{D}$:

$$\mathcal{L}(\theta) = \mathbb{E}_{(o,a) \sim \mathcal{D}}
\left[ -\log \pi_\theta(a \mid o) \right]$$

## 3. Experimente

| Verfahren | Erfolg | Latenz | Parameter |
| --- | --- | --- | --- |
| Vollständiges Modell | 74.8% | 240 ms | 7B |
| Gieriger Ausstieg | 72.0% | 104 ms | 7B |
| Budgetierter Ausstieg (unser Verfahren) | 74.3% | 88 ms | 7B |

![](images/fig1.png)

Erfolgsquote in Abhängigkeit vom durchschnittlichen Rechenaufwand pro Schritt.

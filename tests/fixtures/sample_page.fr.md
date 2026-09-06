# Sortie anticipée sous budget pour les politiques robotiques

## 3. Méthode

### 3.1 Règle de sortie

Les sorties anticipées sont étudiées depuis BranchyNet (Teerapittayanon et al.,
2016), où un seuil de confiance placé sur une couche intermédiaire décide de
l’arrêt. Une politique n’offre aucune confiance de ce type ; nous comparons donc
les actions prédites par deux sorties voisines et nous arrêtons dès qu’elles
concordent.

Soit $o_t$ l’observation au pas $t$ et $a^{(k)}_t$ l’action prédite à la sortie
$k$. La politique sort au premier $k$ vérifiant

$$\lVert a^{(k)}_t - a^{(k-1)}_t \rVert_2 < \alpha$$

avec $\alpha = 0.15$ partout. La règle ne requiert aucun réseau propre : les deux
actions sont déjà calculées lors du passage dans le réseau dorsal
(Vaswani et al., 2017).

## 4. Expériences

| Méthode | Succès | Latence | GFLOPs | Paramètres |
| --- | --- | --- | --- | --- |
| Modèle complet (Brohan et al., 2023) | 74.8% | 240 ms | 31.2 | 7B |
| Demi-profondeur fixe | 68.1% | 121 ms | 15.6 | 7B |
| Sortie gloutonne | 72.0% | 104 ms | 11.4 | 7B |
| Sortie sous budget (notre méthode) | 74.3% | 88 ms | 9.7 | 7B |

![](images/fig1.png)

Taux de succès en fonction du calcul moyen consacré à chaque pas.

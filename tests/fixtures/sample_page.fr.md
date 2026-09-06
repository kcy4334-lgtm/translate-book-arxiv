# Sortie anticipée sous budget pour les politiques robotiques

## 1. Introduction

Une politique robotique fondée sur un grand modèle multimodal consacre la même
quantité de calcul à chaque pas, que la pince traverse un espace vide ou se
referme sur une poignée. Cet article se demande si elle peut décider, à chaque
pas, quelle part de son propre réseau exécuter.

### 1.1 Contributions

- Une règle de sortie qui lit l’accord entre deux prédictions internes voisines.
- Un allocateur de budget qui répartit ce qu’il reste sur les pas restants.

## 2. Méthode

Soit $o_t$ l’observation au pas $t$ et $\pi_\theta$ la politique. L’objectif
d’entraînement est la perte usuelle de clonage comportemental sur un ensemble
de démonstrations $\mathcal{D}$ :

$$\mathcal{L}(\theta) = \mathbb{E}_{(o,a) \sim \mathcal{D}}
\left[ -\log \pi_\theta(a \mid o) \right]$$

## 3. Expériences

| Méthode | Succès | Latence | Paramètres |
| --- | --- | --- | --- |
| Modèle complet | 74.8 % | 240 ms | 7B |
| Sortie gloutonne | 72.0 % | 104 ms | 7B |
| Sortie sous budget (notre méthode) | 74.3 % | 88 ms | 7B |

![](images/fig1.png)

Taux de succès en fonction du calcul moyen consacré à chaque pas.

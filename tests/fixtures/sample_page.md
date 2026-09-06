# Budgeted Early Exit for Robot Policies

## 3. Method

### 3.1 Exit rule

Early exits have been studied since BranchyNet (Teerapittayanon et al., 2016),
where a confidence threshold at an intermediate layer decides whether to stop.
A policy has no such confidence to read, so we compare the actions two
adjacent exits predict and stop once they agree.

Let $o_t$ be the observation at step $t$ and $a^{(k)}_t$ the action predicted
at exit $k$. The policy leaves at the first $k$ satisfying

$$\lVert a^{(k)}_t - a^{(k-1)}_t \rVert_2 < \alpha$$

with $\alpha = 0.15$ throughout. The rule needs no network of its own: both
actions are already computed on the way through the backbone
(Vaswani et al., 2017).

## 4. Experiments

| Method | Success | Latency | GFLOPs | Parameters |
| --- | --- | --- | --- | --- |
| Full model (Brohan et al., 2023) | 74.8% | 240 ms | 31.2 | 7B |
| Fixed half-depth | 68.1% | 121 ms | 15.6 | 7B |
| Greedy exit | 72.0% | 104 ms | 11.4 | 7B |
| Budgeted exit (ours) | 74.3% | 88 ms | 9.7 | 7B |

![](images/fig1.png)

Success rate against the average computation spent per step.

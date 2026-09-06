# Budgeted Early Exit for Robot Policies

## 1. Introduction

A robot policy built on a large multimodal model spends the same computation on
every step, whether the gripper is crossing empty space or closing on a handle.
This paper asks whether it can decide, at each step, how much of its own
network to run.

### 1.1 Contributions

- An exit rule reading the agreement between two adjacent internal predictions.
- A budget allocator that spends what is left over the steps that remain.

## 2. Method

Let $o_t$ be the observation at step $t$ and $\pi_\theta$ the policy. The
training objective is the usual behaviour-cloning loss over a demonstration
set $\mathcal{D}$:

$$\mathcal{L}(\theta) = \mathbb{E}_{(o,a) \sim \mathcal{D}}
\left[ -\log \pi_\theta(a \mid o) \right]$$

## 3. Experiments

| Method | Success | Latency | Parameters |
| --- | --- | --- | --- |
| Full model | 74.8% | 240 ms | 7B |
| Greedy exit | 72.0% | 104 ms | 7B |
| Budgeted exit (ours) | 74.3% | 88 ms | 7B |

![](images/fig1.png)

Success rate against the average computation spent per step.

# PyLean
This is a simple wrapper around [lean-gym](https://github.com/openai/lean-gym) - an environment for proof search of mathematical statements formalized in [Lean 3](https://leanprover.github.io/).

# Installation
1) Install [lean-gym](https://github.com/openai/lean-gym)
2) Install this package with the following command

```
pip install git+https://github.com/yeahrmek/pylean
```

# Example
Assuming that `lean-gym` has been installed in `../lean-gym` directory, the proof search
```python
from pylean import LeanEnv


# Provide name of theorem we would like to prove
env = LeanEnv('../lean-gym', decl='int.prime.dvd_mul')

# initial observation: (state_id, goal)
observation, info = env.reset(return_info=True)

# action is a tuple: (state_id, tactic)
action = (observation[0], 'intros')

# proof step
observation, reward, done, info = env.step(action)

# Complete proof
observation, reward, done, info = env.step(
    (observation[0], 'apply (nat.prime.dvd_mul hp).mp'))
observation, reward, done, info = env.step(
    (observation[0], 'rw ← int.nat_abs_mul'))
observation, reward, done, info = env.step(
    (observation[0], 'exact int.coe_nat_dvd_left.mp h'))

# If proof is complete, the returned state is "no goals"
print(observation[1])
```

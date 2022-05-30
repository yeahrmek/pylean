from typing import Tuple, Optional, Union

from gym import Env

from .lean import LeanInstance


class LeanEnv(LeanInstance, Env):
    """
    Lean environment for proving given theorem.
    It requires openai/lean-gym to be installed (https://github.com/openai/lean-gym)

    Args:
    -----
        lean_gym_path : path-like,
            Path to the lean-gym directory

        decl : str
            Theorem name to be proved. It should be visible by lean-gym
            (see https://github.com/openai/lean-gym)

        timeout : int, default=120
            Timeout for lean commands execution
    """
    reward_range = (0.0, 1.0)

    def __init__(self, *args, decl: Optional[str] = None, **kwargs) -> None:
        assert decl is not None, "Declaration is not provided."
        super().__init__(*args, **kwargs)
        self.decl = decl
        self.search_id = None

    def step(self, action: Tuple[int, str]) -> dict:
        """
        Run given tactic for a given search at given state

        Args:
        -----
            action : Tuple[int, str]
                State id and tactic to apply

        Returns:
        --------
            observation : Tuple(int, str)
                New state id and its string represenation (new goals).
                If tactic application fails it returns `(-1, '')`

            reward : float
                0 - for incorrect tactic or if proof is not complete
                1 - if no goals returned

            done : bool
                End of proof flag

            info : dict
                Dictionary with additional info
                (error, search_id, tactic_state_id, tactic_state, proof_steps)
        """
        state_id, tactic = action
        info = super().run_stmt(self.search_id, state_id, tactic)
        observation, reward, done = (-1, ''), 0, False
        if info['error'] is None:
            observation = (info['tactic_state_id'], info['tactic_state'])
            reward = float(info['tactic_state'] == "no goals")
            done = info['tactic_state'] == "no goals"
        return observation, reward, done, info

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        return_info: bool = False,
        options: Optional[dict] = None,
    ) -> Union[str, Tuple[str, dict]]:
        """
        Reset the environment to an initial state and returns initial observation

        Args:
        ----
            seed : Optional[int], default=None
                The seed that is used to initialize the environment.
                Does not take effect in current evnironment

            return_info : bool, default=False
                If `True` --- additional dictionary with info will be returned

            options : Optional[dict], default=None
                Additional options to initialize environment with.
                Does not take effect currently.
                In future it can be used to initialize env with different theorems.
        """
        if self.search_id is not None:
            self.clear_search(self.search_id)
        info = self.init_search(self.decl)
        self.search_id = None
        observation = (-1, '')
        if info['error'] is None:
            observation = (int(info['tactic_state_id']), info['tactic_state'])
            self.search_id = int(info['search_id'])

        if return_info:
            return observation, info
        return observation

    def close(self):
        """
        Perform any necessary cleanup
        """
        self.kill()


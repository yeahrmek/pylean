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
        super().__init__(*args, **kwargs)
        self._reset_params()
        self.decl = decl

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
            observation = (int(info['tactic_state_id']), info['tactic_state'])
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
        Returns initial observation

        Args:
        ----
            seed : Optional[int], default=None
                The seed that is used to initialize the environment.
                Does not take effect in current evnironment

            return_info : bool, default=False
                If `True` --- additional dictionary with info will be returned

            options : Optional[dict], default=None
                Additional options to initialize environment with.
                It should contain `decl` key with theorem declaration as a value

        Returns:
        --------

        """
        if (self.decl is None and options is None) or (options and not 'decl' in options):
            raise ValueError('Declaration name is not provided.')

        if options:
            self._reset_params()
            self.decl = options['decl']

        if self.search_id is None or self._init_obs[0] == -1:
            info = self.init_search(self.decl)
            if info['error'] is None:
                self._init_obs = (int(info['tactic_state_id']), info['tactic_state'])
                self.search_id = int(info['search_id'])
                self._init_info = info
            else:
                self._init_obs = (-1, '')
                self._init_info = info

        if return_info:
            return self._init_obs, self._init_info
        return self._init_obs

    def close(self):
        """
        Perform any necessary cleanup
        """
        self._reset_params()
        self.kill()

    def clear_search(self):
        """
        Clear proof search state
        """
        super().clear_search(self.search_id)
        self._reset_params()

    def _reset_params(self):
        """
        Reset some internal parameters to empty values
        """
        self.search_id = None
        self.decl = None
        self._init_obs = (-1, '')
        self._init_info = None

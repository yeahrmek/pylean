from typing import Optional, Tuple, Union

from .lean import LeanInstance


class ProofState:
    def __init__(
        self,
        state: Optional[str] = None,
        state_id: Optional[str] = None,
        score: Optional[float] = float('-inf'),
    ):
        self.state = state
        self.id = state_id
        self.score = score

    def __repr__(self) -> str:
        return f"state_id: {self.id}\nstate: {self.state}\nscore: {self.score:.3f}"


class Action:
    def __init__(
        self,
        state_id: Optional[str] = None,
        tactic: Optional[str] = None,
        score: Optional[float] = float('-inf'),
    ):
        self.state_id = state_id
        self.tactic = tactic
        self.score = score

    def __repr__(self) -> str:
        return f"state_id: {self.state_id}\ntactic: {self.tactic}\nscore: {self.score:.3f}"


class LeanEnv(LeanInstance):
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

    def __init__(self, *args, decl: Optional[str] = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._reset_params()
        self.decl = decl

    def step(self, action: Action) -> Tuple[ProofState, float, bool, dict]:
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
        observation, reward, done = ProofState(), 0, False

        info = super().run_stmt(self.search_id, action.state_id, action.tactic)
        if not self.is_error(info):
            observation = ProofState(info["tactic_state"], info["tactic_state_id"])
            reward = float(info["tactic_state"] == "no goals")
            done = info["tactic_state"] == "no goals"

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
        if (self.decl is None and options is None) or (
            options and not "decl" in options
        ):
            raise ValueError("Declaration name is not provided.")

        if options:
            self._reset_params()
            self.decl = options["decl"]

        if self.search_id is None or self._init_obs.state_id is None:
            info = self.init_search(self.decl)
            self._init_info = info
            self._init_obs = ProofState()
            if info["error"] is None:
                self._init_obs = ProofState(
                    info["tactic_state"], info["tactic_state_id"]
                )
                self.search_id = info["search_id"]

        if return_info:
            return self._init_obs, self._init_info
        return self._init_obs

    def close(self) -> None:
        """
        Perform any necessary cleanup
        """
        self._reset_params()
        self.kill()

    def clear_search(self) -> dict:
        """
        Clear proof search state
        """
        decl = self.decl
        out = None
        if self.search_id is not None:
            out = super().clear_search(self.search_id)
        self._reset_params()
        self.decl = decl
        return out

    def _reset_params(self) -> None:
        """
        Reset some internal parameters to empty values
        """
        self.search_id = None
        self.decl = None
        self._init_obs = ProofState()
        self._init_info = None

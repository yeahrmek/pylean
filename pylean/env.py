from typing import Tuple, Optional, Union, List

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

    def step(self,
             action: Tuple[int, str]
    ) -> Tuple[Tuple[int, str], float, bool, dict]:
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

        # # check whether such action has already been performed
        observation, reward, done, info = self._observation_from_cache(
            self.search_id, state_id, tactic)
        if observation is None:
            observation, reward, done, info = self._observation_from_run_stmt(
                self.search_id, state_id, tactic)

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
        decl = self.decl
        super().clear_search(self.search_id)
        self._reset_params()
        self.decl = decl

    def _reset_params(self):
        """
        Reset some internal parameters to empty values
        """
        self.search_id = None
        self.decl = None
        self._init_obs = (-1, '')
        self._init_info = None

    def _observation_from_cache(
        self,
        search_id: int,
        state_id: int,
        tactic: str
    ) -> Tuple[Tuple[int, str], float, bool, dict]:
        search = self.proof_searchs[search_id]
        observation, reward, done, info = None, None, None, None
        if state_id in search['states'] and \
            search['states'][state_id]['tactic'] == tactic:
                id_next = search['states'][state_id]['id_next']
                observation = (id_next, search['states'][id_next]['state'])
                reward = float(observation[1] == "no goals")
                done = float(observation[1] == "no goals")
                info = {
                    'error': None,
                    'search_id': search_id,
                    'tactic_state': observation[1],
                    'tactic_state_id': observation[0]
                }
        return observation, reward, done, info

    def _observation_from_run_stmt(self,
        search_id: int,
        state_id: int,
        tactic: str
    ) -> Tuple[Tuple[int, str], float, bool, dict]:
        info = super().run_stmt(search_id, state_id, tactic)
        observation, reward, done = (-1, ''), 0, False
        if info['error'] is None:
            observation = (int(info['tactic_state_id']), info['tactic_state'])
            reward = float(info['tactic_state'] == "no goals")
            done = info['tactic_state'] == "no goals"
        return observation, reward, done, info


class VectorizedLeanEnv(LeanEnv):
    def __init__(self, *args, decls_list: Optional[str] = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._reset_params()
        self.decls_list = decls_list

    def step(
        self,
        actions_list: List[Tuple[int, int, str]]
    ) -> Tuple[List[Tuple[int, str]], List[float], List[bool], List[dict]]:
        """
        Run given tactic for a given search at given state

        Args:
        -----
            actions : List[Tuple[int, str]]
                State id and tactic to apply for each statement.
                List length should be equal to the length of the `decls_list`

        Returns:
        --------
            observation : List[Tuple(int, str)]
                New state id and its string represenation (new goals).
                If tactic application fails it returns `[(-1, '')]`

            reward : List[float]
                0 - for incorrect tactic or if proof is not complete
                1 - if no goals returned

            done : List[bool]
                End of proof flag

            info : List[dict]
                Dictionary with additional info
                (error, search_id, tactic_state_id, tactic_state, proof_steps)
        """
        observations, rewards, dones, infos = [], [], [], []

        run_indices = []
        # check whether such action has already been performed
        for i, (search_id, action) in enumerate(zip(self.search_id_list, actions_list)):
            obs_cur, reward_cur, done_cur, info_cur = self._observation_from_cache(
                search_id, *action)
            observations.append(obs_cur)
            rewards.append(reward_cur)
            dones.append(done_cur)
            infos.append(info_cur)
            if obs_cur is None:
                run_indices.append(i)

        run_search_ids = [self.search_id_list[i] for i in run_indices]
        run_state_ids = [actions_list[i][0] for i in run_indices]
        run_tactics = [actions_list[i][1] for i in run_indices]

        output = self.run_batch(run_search_ids, run_state_ids, run_tactics)

        for i, search_id in zip(run_indices, run_search_ids):
            observations[i], rewards[i], dones[i] = (-1, ''), 0, False
            infos[i] = output[search_id]
            if infos[i]['error'] is None:
                observations[i] = (int(infos[i]['tactic_state_id']), infos[i]['tactic_state'])
                rewards[i] = float(infos[i]['tactic_state'] == "no goals")
                dones[i] = infos[i]['tactic_state'] == "no goals"

        return observations, rewards, dones, infos

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
        if (self.decls_list is None and options is None) or (options and not 'decls_list' in options):
            raise ValueError('Declaration name is not provided.')

        if options:
            self._reset_params()
            self.decls_list = options['decls_list']

        if self.search_id_list is None or self._init_obs[0][0] == -1:
            self.search_id_list = []
            self._init_obs = []
            self._init_info = []
            for decl in self.decls_list:
                info = self.init_search(decl)
                if info['error'] is None:
                    self._init_obs.append((int(info['tactic_state_id']), info['tactic_state']))
                    self.search_id_list.append(int(info['search_id']))
                    self._init_info.append(info)
                else:
                    self._init_obs.append((-1, ''))
                    self._init_info.append(info)
                    self.search_id_list.append(None)

        if return_info:
            return self._init_obs, self._init_info
        return self._init_obs

    def clear_search(self):
        """
        Clear proof search state
        """
        decls_list = self.decls_list
        [super(LeanEnv, self).clear_search(search_id) for search_id in self.search_id_list]
        self._reset_params()
        self.decls_list = decls_list

    def _reset_params(self):
        self.search_id_list = None
        self.decls_list = None
        self._init_obs = [(-1, '')]
        self._init_info = None

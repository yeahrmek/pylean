import threading
import subprocess
import queue
import json

from typing import Optional


class LeanException(Exception):
    pass


class LeanInstance(threading.Thread):
    """
    """
    def __init__(self, lean_gym_path: str, timeout: int = 120,
                 verbose: int = 0) -> None:
        self.lean_gym_path = lean_gym_path
        self.command = ['lean', '--run', 'src/repl.lean']
        self.timeout = timeout
        self.verbose = verbose
        self.__sema = threading.Semaphore(value=0)
        threading.Thread.__init__(self, daemon=True)
        # Open a process to lean, with streams for communicating with
        # it.
        self._proc = subprocess.Popen(self.command,
                                      cwd=self.lean_gym_path,
                                      stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
        self._fout = self._proc.stdout
        self._fin = self._proc.stdin

        self.proof_searchs = {}  # search_id -> dict(state_id -> proof_context)
        self.statistics = {}

        # Set up the message queue, which we'll populate with the
        # messages from lean-gym.
        self.message_queue = queue.Queue()

        # Start the message queue thread
        self.start()

    def init_search(self, decl: str) -> dict:
        """
        Initialize lean for the given declaration of the statement
        """
        self._send_flush(f'["init_search", ["{decl}", ""]]\n')
        result = self.get_result()
        # {"error":null,
        #  "proof_steps":[],
        #  "search_id":"0",
        #  "tactic_state":"⊢ ∀ {m n : ℤ} {p : ℕ}, nat.prime p → ↑p ∣ <...>,
        #  "tactic_state_id":"0"}
        if result['error'] is None:
            search_id = int(result['search_id'])
            tactic_state_id = int(result['tactic_state_id'])
            self.proof_searchs[search_id] = {
                'decl': decl,
                'states': {
                    tactic_state_id: {
                        'id_prev': None,
                        'id_next': None,
                        'state_after': result['tactic_state'],
                        'tactic': None
                    }
                },
                'n_failed_tactics': 0,
                'n_total_tactics': 0
            }

        return result

    def run_stmt(self, search_id: int, state_id: int, tactic: str) -> dict:
        """
        Run given tactic for a given search at given state
        """
        cmd = f'["run_tac",["{search_id}","{state_id}","{tactic}"]]\n'

        self._send_flush(cmd)
        results = self.get_result()
        self.update_proof_search(search_id, state_id, tactic, results)
        return results

    def run_batch(self, search_ids: list[int], state_ids: list[int],
                  tactics: list[str]) -> dict:
        """
        Run a batch of given tactics. We can do it only if
        all search_ids are different. Can't parallelize tactics
        inside the same proof search
        """
        assert len(search_ids) == len(set(search_ids)), \
            "Attempt to parallelize the same proof search."

        # search_ids are unique
        ids_map = {}

        for s_id, tac_id, tac in zip(search_ids, state_ids, tactics):
            ids_map[s_id] = (int(tac_id), tac)
            cmd = f'["run_tac",["{s_id}","{tac_id}","{tac}"]]\n'
            self._send_flush(cmd)
        output = {}
        for _ in range(len(search_ids)):
            result = self.get_result()
            if result['search_id'] is not None:
                search_id = int(result['search_id'])
                state_id_before, tactic = ids_map[search_id]
                self.update_proof_search(search_id, state_id_before, tactic, result)
                del ids_map[search_id]
            output[result['search_id']] = result
        for search_id in ids_map:
            self.proof_searchs[search_id]['n_failed_tactics'] += 1
            self.proof_searchs[search_id]['n_total_tactics'] += 1
        return output

    def clear_search(self, search_id: int) -> dict:
        self._send_flush(f'["clear_search",["{search_id}"]]\n')
        del self.proof_searchs[search_id]
        return self.get_result()

    def get_result(self, timeout: Optional[int] = None) -> dict:
        timeout = timeout if timeout else self.timeout
        try:
            msg = self.message_queue.get(timeout=self.timeout)
            assert msg is not None
            return json.loads(msg)
        except queue.Empty:
            print("Command timed out! Interrupting")

    def get_tactic_state(self, search_id: int, state_id: int) -> dict:
        return self.proof_searchs[search_id]['states'][state_id]

    def get_tactic_after(self, search_id: int, state_id: int) -> str:
        id_next = self.proof_searchs[search_id]['states'][state_id]['id_next']
        return self.proof_searchs[search_id]['states'][id_next]['tactic']

    def update_proof_search(self, search_id: int, state_id_previous: int,
                            tactic: str, result: dict) -> None:
        if result['error'] is None:
            state_id = int(result['tactic_state_id'])
            self.proof_searchs[search_id]['states'][state_id] = {
                'id_prev': state_id_previous,
                'id_next': None,
                'state_after': result['tactic_state'],
                'tactic': tactic
            }
            self.proof_searchs[search_id]['states']\
                [state_id_previous]['id_next'] = state_id
        else:
            self.proof_searchs[search_id]['n_failed_tactics'] += 1
        self.proof_searchs[search_id]['n_total_tactics'] += 1

    def _send_flush(self, cmd: str) -> None:
        assert self._fin
        try:
            self._fin.write(cmd.encode('utf-8'))
            self._fin.flush()
        except BrokenPipeError:
            raise LeanException("Lean process unexpectedly quit.")

    def run(self) -> None:
        assert self._fout
        while not self.__sema.acquire(False):
            try:
                line = self._fout.readline().decode('utf-8')
            except ValueError:
                continue
            if line.strip() == '':
                break
            self.message_queue.put(line)

    def kill(self) -> None:
        assert self._proc.stdout
        self._proc.terminate()
        self._proc.kill()
        self.__sema.release()

import json
import queue
import subprocess
import threading
from typing import List, Optional


class LeanException(Exception):
    pass


class LeanInstance(threading.Thread):
    """ """

    def __init__(
        self, lean_gym_path: str, timeout: int = 300, verbose: int = 0
    ) -> None:
        self.lean_gym_path = lean_gym_path
        self.command = ["lean", "--run", "src/repl.lean"]
        self.timeout = timeout
        self.verbose = verbose
        self.__sema = threading.Semaphore(value=0)
        threading.Thread.__init__(self, daemon=True)
        # Open a process to lean, with streams for communicating with
        # it.
        self._proc = subprocess.Popen(
            self.command,
            cwd=self.lean_gym_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._fout = self._proc.stdout
        self._fin = self._proc.stdin

        self.proof_searchs = {}  # search_id -> dict(state_id -> proof_context)

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
        msg = [self._get_message(self.timeout)]
        while "warning:" in msg[-1]:
            msg.append(self._get_message(self.timeout))
        result = json.loads(msg[-1])

        if result["error"] is None:
            search_id = int(result["search_id"])
            tactic_state_id = int(result["tactic_state_id"])
            self.proof_searchs[search_id] = {
                "decl": decl,
                "states": {
                    tactic_state_id: {
                        "id_prev": [],
                        "state": result["tactic_state"],
                        "tactic_to_next_id": {},
                    }
                },
                "n_failed_tactics": 0,
                "n_total_tactics": 0,
                "failed_tactics": {},
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

    def clear_search(self, search_id: int) -> dict:
        self._send_flush(f'["clear_search",["{search_id}"]]\n')
        result = self.get_result()

        n_msgs = 0
        while (
            result["error"] is not None
            or result["tactic_state"] is not None
            or result["tactic_state_id"] is not None
        ):
            if result['search_id'] is not None:
                assert result['search_id'] == str(search_id), f"{result['search_id']}, {search_id}"
            result = self.get_result(timeout=10)
            n_msgs += 1
        print(f"Collected {n_msgs}")
        print(f"search_id: {search_id}")
        print(result)

        if result["error"] is not None:
            raise RuntimeError(result["error"])

        del self.proof_searchs[search_id]
        print(f"Search_id {search_id} deleted successfully")
        print(f"Current search ids: {list(self.proof_searchs)}")

        return result

    def get_result(self, timeout: Optional[int] = None) -> dict:
        return json.loads(self._get_message(timeout))

    def update_proof_search(
        self, search_id: int, state_id_previous: int, tactic: str, result: dict
    ) -> None:
        if result["error"] is None:
            state_id = int(result["tactic_state_id"])

            states = self.proof_searchs[search_id]["states"]

            states[state_id_previous]["tactic_to_next_id"][tactic] = state_id

            if not state_id in states:
                states[state_id] = {
                    "id_prev": [state_id_previous],
                    "tactic_to_next_id": {},
                }
            else:
                states[state_id]["id_prev"].append(state_id_previous)
            states[state_id]["state"] = result["tactic_state"]
        else:
            self.proof_searchs[search_id]["n_failed_tactics"] += 1
            self.proof_searchs[search_id]["failed_tactics"][tactic] = result["error"]
        self.proof_searchs[search_id]["n_total_tactics"] += 1

    def _send_flush(self, cmd: str) -> None:
        assert self._fin
        try:
            self._fin.write(cmd.encode("utf-8"))
            self._fin.flush()
        except BrokenPipeError:
            raise LeanException("Lean process unexpectedly quit.")

    def run(self) -> None:
        assert self._fout
        while not self.__sema.acquire(False):
            try:
                line = self._fout.readline().decode("utf-8")
            except ValueError:
                continue
            if line.strip() == "":
                break
            self.message_queue.put(line)

    def kill(self) -> None:
        assert self._proc.stdout
        self._proc.terminate()
        self._proc.kill()
        self.__sema.release()

    def _get_message(self, timeout: float) -> str:
        timeout = timeout if timeout else self.timeout
        try:
            msg = self.message_queue.get(timeout=timeout)
            return msg
        except queue.Empty:
            raise queue.Empty("Command time out")

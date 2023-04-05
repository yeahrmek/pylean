import json
import queue
import subprocess
import threading
from typing import Optional


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

        # Set up the message queue, which we'll populate with the
        # messages from lean-gym.
        self.message_queue = queue.Queue()
        self._last_flash_cmd = None

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

        if not self.is_error(result):
            search_id = result["search_id"]
            tactic_state_id = result["tactic_state_id"]

        return result

    def run_stmt(self, search_id: str, state_id: str, tactic: str) -> dict:
        """
        Run given tactic for a given search at given state
        """
        cmd = f'["run_tac",["{search_id}","{state_id}","{tactic}"]]\n'
        self._send_flush(cmd)
        results = self.get_result()
        return results

    def clear_search(self, search_id: str) -> dict:
        self._send_flush(f'["clear_search",["{search_id}"]]\n')
        result = self.get_result(timeout=1)

        if self.is_error(result):
            print(bcolors.WARNING + result['error'] + bcolors.ENDC)
            raise RuntimeError(result['error'])

        return result

    def _send_flush(self, cmd: str) -> None:
        assert self._fin
        self._last_flash_cmd = cmd
        try:
            self._fin.write(cmd.encode("utf-8"))
            self._fin.flush()
        except BrokenPipeError:
            raise LeanException(f"Lean process unexpectedly quit. Last cmd: {cmd}")

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

    def get_result(self, timeout: Optional[float] = None) -> str:
        timeout = timeout if timeout else self.timeout
        return json.loads(self._get_message(timeout=timeout))

    def _get_message(self, timeout: Optional[float] = None) -> str:
        timeout = timeout if timeout else self.timeout
        try:
            msg = self.message_queue.get(timeout=timeout)
            return msg
        except queue.Empty:
            raise queue.Empty(f"Command time out. Last cmd: {self._last_flash_cmd}, timeout={timeout}")

    def is_error(self, result):
        return result['error'] is not None


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


# def validate_proof_search(lean, search_id):
#     from copy import deepcopy

#     assert len(lean.proof_searchs) == 1
#     proof_search = deepcopy(lean.proof_searchs[search_id])
#     for state_id, state in proof_search['states'].items():
#         for tac, next_state_id in state['tactic_to_next_id'].items():
#             res = lean.run_stmt(search_id, state_id, tac)
#             if (res['tactic_state'] != proof_search['states'][next_state_id]['state']
#                 and not (res['tactic_state'] is not None
#                          and '_fresh_' in res['tactic_state']
#                          and '_fresh_' in proof_search['states'][next_state_id]['state'])
#             ):
#                 print(tac)
#                 print(res)
#                 tactics, ids = get_proof_branch(proof_search, next_state_id)
#                 lean2 = LeanInstance(lean_gym_path=lean.lean_gym_path)
#                 lean2.init_search(lean.decl)
#                 i = 0
#                 res2 = []
#                 for t in tactics:
#                     res2.append(lean2.run_stmt(0, i, t))
#                     if res2[-1]['tactic_state_id'] is not None:
#                         i = int(res2[-1]['tactic_state_id'])
#                     else:
#                         breakpoint()
#                         print('sapog')
#                 breakpoint()


# def get_proof_branch(proof_search, last_state_id):

#     tactics = []
#     ids = []
#     while proof_search['states'][last_state_id]['id_prev']:
#         id_prev = proof_search['states'][last_state_id]['id_prev'][0]
#         tac, i = zip(*[(tac, i) for tac, i in proof_search['states'][id_prev]['tactic_to_next_id'].items() if i == last_state_id])
#         tactics.append(tac[0])
#         ids.append(i[0])
#         last_state_id = id_prev

#     return tactics[::-1], ids[::-1]

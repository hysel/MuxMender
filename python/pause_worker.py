"""Linux exec shim: a stopped media worker must not outlive its supervisor."""
import ctypes
import os
import signal
import sys


def main():
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Linux-only media supervisor shim')
    parent, ready = int(sys.argv[1]), int(sys.argv[2])
    command = sys.argv[3:]
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), 'Cannot arm parent-death cleanup')
    if os.getppid() != parent:
        raise RuntimeError('Media supervisor exited before launch')
    os.write(ready, b'R')
    os.close(ready)
    os.execvpe(command[0], command, os.environ)


if __name__ == '__main__':
    main()

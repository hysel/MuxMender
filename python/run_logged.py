"""Optional standalone launcher retaining a unique terminal log for long jobs."""
import sys
import time
import uuid
from pathlib import Path
import muxmender


class Tee:
    def __init__(self, terminal, log):
        self.terminal, self.log = terminal, log

    def write(self, text):
        self.log.write(text)
        self.log.flush()
        return self.terminal.write(text)

    def flush(self):
        self.log.flush()
        self.terminal.flush()

    def __getattr__(self, name):
        return getattr(self.terminal, name)


if __name__ == '__main__':
    folder = Path(__file__).resolve().parent.parent / 'reports'
    folder.mkdir(exist_ok=True)
    path = folder / ('run-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8] + '.log')
    terminal_out, terminal_err = sys.stdout, sys.stderr
    with path.open('x', encoding='utf-8') as log:
        sys.stdout, sys.stderr = Tee(terminal_out, log), Tee(terminal_err, log)
        code = 1
        try:
            print(f'Persistent run log: {path}', flush=True)
            code = muxmender.cli()
        except KeyboardInterrupt:
            print('Cancelled. Originals and partial outputs retained.', flush=True)
            code = 130
        finally:
            print(f'RUN EXIT CODE: {code}', flush=True)
            sys.stdout, sys.stderr = terminal_out, terminal_err
    raise SystemExit(code)

"""Isolate publication tracking/stdout from the multithreaded service."""
import argparse
from pathlib import Path
from job_tracking import tracked_call
from validated_replace import replace_validated


def main():
    parser=argparse.ArgumentParser()
    for name in ('source','media','writable','result','folder'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--minimum',type=float,required=True);parser.add_argument('--job',required=True)
    args=parser.parse_args()
    def run():
        replace_validated(args.source,args.media,args.writable,args.result,args.minimum,args.job)
        return 0
    return tracked_call(run,'Publishing validated replacement',folder=args.folder)


if __name__=='__main__':raise SystemExit(main())

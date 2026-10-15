"""Keep tracked repository content source-only; release bundles live elsewhere."""
from pathlib import Path
import subprocess
import unittest
import re


class RepositoryContentTests(unittest.TestCase):
    def test_no_private_installation_examples(self):
        root=Path(__file__).resolve().parents[1]
        if not (root/'.git').exists():self.skipTest('Source archive has no Git inventory')
        paths=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
        patterns=(rb'/mnt/'+rb'FR4G', rb'192\.168\.1\.(?:232|212|72)\b',
                  rb'[CE]:[/\\]Users[/\\]'+rb'itama', rb'GPU-'+rb'cebbcdda')
        issues=[]
        for name in paths:
            path=root/name
            if not name or not path.is_file():continue
            if any(re.search(pattern,path.read_bytes(),re.I) for pattern in patterns):issues.append(name)
        self.assertEqual(issues,[], 'Private installation examples must stay outside the published source')

    def test_tracked_tree_contains_no_binary_or_generated_artifacts(self):
        root=Path(__file__).resolve().parents[1]
        if not (root/'.git').exists():self.skipTest('Source archive has no Git inventory')
        result=subprocess.run(['git','ls-files','-z'],cwd=root,check=True,capture_output=True)
        forbidden={'.mkv','.mp4','.avi','.mov','.webm','.m2ts','.vob','.mp3','.wav',
                   '.flac','.aac','.ac3','.dts','.hevc','.h264','.h265','.obu','.yuv','.y4m',
                   '.png','.jpg','.jpeg','.gif','.webp','.ico','.exe','.dll','.so','.dylib',
                   '.whl','.zip','.tar','.gz','.xz','.bz2','.7z','.rpm','.deb','.log','.sqlite','.db'}
        problems=[]
        for raw in result.stdout.split(b'\0'):
            if not raw:continue
            relative=raw.decode('utf-8');path=root/relative
            if path.is_symlink():
                problems.append(relative+' (symlink requires review)');continue
            if not path.exists():continue # Pending tracked deletion.
            if path.suffix.lower() in forbidden or '.so.' in path.name.lower():
                problems.append(relative+' (artifact extension)')
            with path.open('rb') as source:
                if any(b'\0' in block for block in iter(lambda:source.read(65536),b'')):
                    problems.append(relative+' (binary content)')
        self.assertEqual(problems,[], '\n'.join(problems))

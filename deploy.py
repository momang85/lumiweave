"""一键：提交+推送+构建exe"""
import subprocess, os, webbrowser
ROOT = r'c:/Users/ding0/Desktop/ai_agent/ai-agent-hub'
os.chdir(ROOT)

def run(cmd, **kw):
    print(f'  > {cmd}')
    cwd = kw.pop('cwd', ROOT)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    for line in (r.stdout + r.stderr).split('\n'):
        if line.strip() and 'warning' not in line.lower():
            print(f'    {line[:120]}')
    return r

print('[1/3] Git commit + push...')
run('git add -A')
run('git commit -m "fix: pip install support"')
run('git remote remove origin')
run('git remote add origin https://github.com/momang85/lumiweave.git')
run('git push -u origin master --force', timeout=30)
run('git push -u origin master:main --force', timeout=30)

print('[2/3] Build exe...')
if not os.path.exists('dist/lumiweave.exe'):
    run('pyinstaller lumiweave.spec', timeout=600)

size = os.path.getsize('dist/lumiweave.exe')//1024//1024 if os.path.exists('dist/lumiweave.exe') else 0
print(f'   EXE: {size}MB')

print('[3/3] Opening GitHub...')
webbrowser.open('https://github.com/momang85/lumiweave')
print('Done!')

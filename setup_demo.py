import os,secrets
from pathlib import Path
p=Path('.env')
if not p.exists():
    p.write_text('\n'.join(f'SENTINEL_{r}_TOKEN={secrets.token_urlsafe(32)}' for r in ('READER','OPERATOR','ADMIN'))+'\n',encoding='utf-8')
    print('Tokens created in .env; do not share or commit them.')
else: print('.env already exists')

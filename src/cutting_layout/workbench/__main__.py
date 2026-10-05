"""Administrative CLI. No credentials are accepted on command lines."""
import argparse
import getpass
import os
from pathlib import Path
from .store import Store
from .maintenance import backup, restore


def main():
    parser = argparse.ArgumentParser(description='MPCOS 内部下料工作台')
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('MPCOS_DATA_DIR', 'var/workbench')))
    commands = parser.add_subparsers(dest='command', required=True)
    user = commands.add_parser('create-user')
    user.add_argument('username')
    user.add_argument('--role', choices=['employee', 'manager'], required=True)
    reset = commands.add_parser('reset-password')
    reset.add_argument('username')
    commands.add_parser('disable-user').add_argument('username')
    serve = commands.add_parser('serve')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8765)
    commands.add_parser('backup').add_argument('destination', type=Path)
    commands.add_parser('restore').add_argument('archive', type=Path)
    args = parser.parse_args()
    if args.command in {'create-user', 'reset-password'}:
        password = getpass.getpass('新密码（至少12字符）：')
        if password != getpass.getpass('重复密码：'):
            parser.error('两次密码不一致。')
        store = Store(args.data_dir)
        if args.command == 'create-user':
            store.create_user(args.username, password, args.role)
        else:
            store.reset_password(args.username, password)
        print('账号操作完成。')
    elif args.command == 'disable-user':
        Store(args.data_dir).disable_user(args.username)
        print('账号已停用，会话已失效；业务记录保留。')
    elif args.command == 'backup':
        print(backup(args.data_dir, args.destination))
    elif args.command == 'restore':
        print(restore(args.archive, args.data_dir))
    else:
        import uvicorn
        from .app import create_app
        uvicorn.run(create_app(args.data_dir), host=args.host, port=args.port, workers=1, access_log=False)


if __name__ == '__main__':
    main()

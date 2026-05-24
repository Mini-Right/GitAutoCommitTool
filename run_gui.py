import sys
sys.argv = [sys.argv[0], "--gui"]

from git_auto_commit.__main__ import main

if __name__ == "__main__":
    main()

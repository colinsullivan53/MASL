"""CLI entry point for MASL. Run with: python -m src <file.masl>"""
import argparse
import os
import sys

from src.lexer import Lexer, LexerError
from src.parser import Parser, ParseError
from src.compiler import compile_match, CompilerError
from src.scheduler import Scheduler
from src.runner import Runner


def main():
    parser = argparse.ArgumentParser(description="MASL - Melee Action Scripting Language")
    parser.add_argument("file", help="Path to .masl file")
    parser.add_argument("--dry-run", action="store_true", help="Run without Dolphin")
    parser.add_argument("--frames", type=int, default=60, help="Frames for dry-run (default: 60)")
    parser.add_argument("--dolphin", help="Path to Dolphin executable")
    parser.add_argument("--iso", help="Path to Melee ISO")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    try:
        with open(args.file) as f:
            source = f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    try:
        base_path = os.path.dirname(os.path.abspath(args.file))
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens, base_path=base_path).parse()
        queues = compile_match(ast)

        scheduler = Scheduler()
        for port, queue in queues.items():
            scheduler.load(port, queue)

        if args.dry_run:
            runner = Runner(scheduler)
            results = runner.dry_run(args.frames)
            from src.compiler import InputFrame
            for i, frame_data in enumerate(results):
                active_ports = {p: f for p, f in frame_data.items()
                               if f != InputFrame()}
                if active_ports or args.debug:
                    print(f"Frame {i}: {active_ports if active_ports else 'neutral'}")
        else:
            if not args.dolphin or not args.iso:
                print("Error: --dolphin and --iso required for live execution", file=sys.stderr)
                sys.exit(1)
            runner = Runner(scheduler, args.dolphin, args.iso, ast.game)
            runner.run()

    except (LexerError, ParseError, CompilerError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import getpass
import sys
import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.features.identity.security import hash_password


def _resolve_actor():
    candidates = [
        "app.features.identity.models",
        "app.features.identity.model",
        "app.db.models",
        "app.models",
        "app.db.model",
    ]
    for mod in candidates:
        try:
            m = __import__(mod, fromlist=["Actor"])
            a = getattr(m, "Actor", None)
            if a is not None:
                return a
        except Exception:
            continue
    try:
        from app.db.base import Base

        def _all_subs(cls):
            for sub in cls.__subclasses__():
                yield sub
                yield from _all_subs(sub)

        for c in _all_subs(Base):
            if getattr(c, "__tablename__", None) == "actors":
                return c
    except Exception:
        pass
    raise ImportError("Actor model not found")


Actor = _resolve_actor()


def do_bootstrap_owner(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        existing = db.execute(select(Actor).where(Actor.kind == "owner", Actor.active.is_(True))).scalars().first()
        if existing is not None:
            print("owner already bootstrapped", file=sys.stderr)
            sys.exit(1)
        display_name = getattr(args, "display_name", None)
        if not display_name:
            try:
                display_name = input("display_name: ").strip()
            except EOFError:
                print("cancelled", file=sys.stderr)
                sys.exit(1)
        else:
            display_name = str(display_name).strip()
        if not display_name:
            print("display_name is required", file=sys.stderr)
            sys.exit(1)
        try:
            pw1 = getpass.getpass("password: ")
            pw2 = getpass.getpass("password (confirm): ")
        except (EOFError, KeyboardInterrupt):
            print("\ncancelled", file=sys.stderr)
            sys.exit(1)
        if not pw1 or not pw2:
            print("password is required", file=sys.stderr)
            sys.exit(1)
        if pw1 != pw2:
            print("passwords do not match", file=sys.stderr)
            sys.exit(1)
        if len(pw1) < 8:
            print("password must be at least 8 characters", file=sys.stderr)
            sys.exit(1)
        actor = Actor(
            id=uuid.uuid4(),
            kind="owner",
            display_name=display_name,
            password_hash=hash_password(pw1),
            active=True,
        )
        db.add(actor)
        db.commit()
        db.refresh(actor)
        print(f"owner created: id={actor.id} display_name={actor.display_name}")
    finally:
        try:
            db.close()
        except Exception:
            pass


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("bootstrap-owner", help="bootstrap initial owner")
    p.add_argument("--display-name", dest="display_name", default=None, help="owner display name")
    p.set_defaults(func=do_bootstrap_owner)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

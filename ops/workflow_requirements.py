"""Operator-only required-route configuration; inspect unless --apply is explicit."""

import argparse
import os
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type-id", required=True)
    parser.add_argument("--template-id", required=True)
    parser.add_argument(
        "--classification",
        default="*",
        choices=["*", "PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"],
        help="Exact document classification; '*' (default) covers classifications without their own route",
    )
    parser.add_argument("--reviewer-roles", nargs="+", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    roles = sorted(set(args.reviewer_roles))
    if (
        not set(roles) <= {"USER", "REVIEWER", "APPROVER", "LEGAL", "MANAGER", "ADMIN"}
        or len(args.reason.strip()) < 3
    ):
        parser.error("Known reviewer roles and a business reason required")
    with psycopg.connect(os.environ["NEXORA_WORKFLOW_OPERATOR_URL"]) as conn:
        if conn.execute("SELECT current_user").fetchone()[0] != "nexora_migrations":
            raise RuntimeError("Dedicated migrations operator required")
        conn.execute("SET LOCAL lock_timeout='5s'")
        definition = conn.execute(
            "SELECT definition FROM workflow_templates WHERE id=%s", (args.template_id,)
        ).fetchone()
        if not definition or any(s.get("conditions") for s in definition[0]["stages"]):
            raise RuntimeError("Required route must have existing unconditional stages")
        if not conn.execute("SELECT 1 FROM document_types WHERE id=%s", (args.type_id,)).fetchone():
            raise RuntimeError("Existing document type required")
        print("Requirement validated; " + ("apply" if args.apply else "inspect only"))
        if not args.apply:
            conn.rollback()
            return
        conn.execute(
            "INSERT INTO workflow_requirements(type_id,classification,template_id,reviewer_roles) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT(type_id,classification) "
            "DO UPDATE SET template_id=EXCLUDED.template_id,reviewer_roles=EXCLUDED.reviewer_roles",
            (args.type_id, args.classification, args.template_id, Jsonb(roles)),
        )
        conn.execute(
            "INSERT INTO audit_events(id,actor_id,action,target_type,target_id,safe_metadata,request_id) "
            "VALUES (%s,NULL,%s,%s,%s,%s,%s)",
            (
                str(uuid4()),
                "WORKFLOW_REQUIREMENT_UPDATED",
                "document_type",
                args.type_id,
                Jsonb({"template_id": args.template_id, "classification": args.classification,
                       "reviewer_roles": roles, "reason": args.reason}),
                str(uuid4()),
            ),
        )


if __name__ == "__main__":
    main()

"""Rule layer: fixed, non-learned checks over roles and taint labels."""
from __future__ import annotations

from .core import ROLE_TOOLS, TRUSTED_DOMAINS, domain


def check(agent: str, tool: str, untrusted: bool, sens: int, to: str | None) -> str:
    """Return the first violated rule id, or '' if the action is rule-compliant.

    R1 capability:    an agent may only call the tools its role grants.
    R2 control flow:  data from an untrusted source may not trigger a sensitive action
                      (reading personal records, or emailing an unknown recipient).
    R3 data flow:     internal or personal data may not leave to an unknown recipient.
    """
    if tool != "send_msg" and tool not in ROLE_TOOLS[agent]:
        return "R1"
    external = to is not None and domain(to) not in TRUSTED_DOMAINS
    if untrusted and (tool == "db_record" or (tool == "send_email" and external)):
        return "R2"
    if tool == "send_email" and external and sens >= 1:
        return "R3"
    return ""

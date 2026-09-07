# ES Signup

Approval-gated account sign-up for ES ERP sites. A visitor asks for an account,
you get an email, you approve it, and the account is created — as either a
customer portal user or a staff System User.

Built for Frappe v15 (tested against 15.103) with optional ERPNext integration.

## What it adds

| Thing | Name | Notes |
|---|---|---|
| DocType | **ES Signup Request** | One record per request, with full audit trail |
| Single DocType | **ES Signup Settings** | Per-site config: approvers, roles, domains, copy |
| Child table | **ES Signup Role** | Role rows inside settings |
| Role | **ES Signup Approver** | Can read and action requests |
| Workflow | **ES Signup Approval** | Pending Approval → Approved / Rejected / Cancelled |
| Portal page | `/signup` | Public form |
| Portal page | `/signup-action` | Confirmation screen the email links open |
| Override | `signup_form_template` | Replaces the login page's signup card with a handoff to `/signup` |
| Override | `frappe...user.sign_up` | Backstop: direct API sign-ups land in the same queue |

## Install

```bash
cd ~/frappe-bench

# once per bench
bench get-app es_signup /path/to/es_signup   # or a git remote

# once per site
bench --site enterprisesystems.com.au install-app es_signup
bench --site demo.enterprisesystems.com.au install-app es_signup
bench --site demo2.enterprisesystems.com.au install-app es_signup

bench --site enterprisesystems.com.au clear-cache
bench build --app es_signup
```

`after_install` creates the role and workflow, seeds
`james.rempel@enterprisesystems.com.au` as the approver, and leaves
**Enable Sign-Up Requests unticked** so nothing goes live until you say so.

## Configure

Open **ES Signup Settings** on each site and set:

- **Approver Emails** — one per line. Everyone listed gets the email; the first
  to action it wins.
- **Customer (Website User) Roles** / **System User Roles** — what gets granted
  on approval. Keep the System User list narrow; those consume licensed seats.
- **Allowed / Blocked Email Domains** — leave allowed blank to accept anyone.
- **Enable Sign-Up Requests** — tick when you're ready.

Then confirm outgoing email works on the site, since the whole flow depends on it:

```bash
bench --site enterprisesystems.com.au console
>>> frappe.sendmail(recipients=["james.rempel@enterprisesystems.com.au"], subject="test", message="test", now=True)
```

## The flow

1. Visitor submits `/signup`. The old `/login#signup` link now redirects there,
   and the "Sign up" links on the login page point at `/signup` directly.
2. An **ES Signup Request** is created with status `Pending Approval` and a
   one-time action token. Rate limited to 3 per email and per IP per hour, with
   a honeypot field and duplicate/existing-user checks.
3. The approvers get an email with the details and two links.
4. The link opens a confirmation page showing the request. **The GET renders;
   only the POST from that page acts** — so Outlook, Proofpoint and other link
   scanners can't approve an account by prefetching.
5. On approval the request status flips to `Approved`, which triggers
   `on_update` → account provisioning.
6. The applicant gets a welcome email with a password-reset link. No password is
   ever generated or transmitted.

Approving from the desk button, from the workflow dropdown, or from the email
link all set the same `status` field, so they all converge on the same
provisioning code path.

## What gets created on approval

**Customer**
- `User` with `user_type = Website User`, roles from settings (falls back to
  Portal Settings' default role)
- `Customer` — named from the company field, or the person's name if blank
- `Contact` linked to both the User and the Customer

**System User**
- `User` with `user_type = System User` and roles from settings
- No Customer or Contact

Turn Customer/Contact creation off in settings if you'd rather link records by
hand.

## Security notes

- Guest holds no DocPerms on ES Signup Request. Guest requests come in through
  whitelisted methods that insert with `ignore_permissions`.
- Action tokens are stored as a SHA-256 hash; only the plaintext goes in the
  email, and it's cleared once used. Default validity is 7 days, configurable.
- Anyone holding an approval link can approve. If that's too loose for the
  production site, set **Email Link Validity** short and rely on the desk
  buttons — or put the `/signup-action` route behind your reverse proxy's auth.
- `process_email_action` is POST-only and rate limited.

## Uninstall

```bash
bench --site <site> uninstall-app es_signup
```

Users and Customers already created stay put; only the request records go.

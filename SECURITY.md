# Security Policy

## Reporting Security Issues

Please do not publish secrets, cookies, or exploit details in public issues.

If you find a security problem, open a private report if GitHub private vulnerability reporting is enabled, or contact the repository owner directly before sharing technical details publicly.

## Secret Handling

- Do not commit `.ROBLOSECURITY` cookies.
- Store cookies in environment variables only for local testing.
- Rotate any cookie that was exposed in terminal logs, screenshots, commits, or chat messages.
- Prefer Roblox Open Cloud credentials for production automation.

## Supported Usage

This project is intended for managing your own Roblox places. Do not use it to access accounts, assets, or experiences you do not own or have permission to manage.

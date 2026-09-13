# CSMS V2 UI Foundation

This phase adds a server-rendered web UI on top of the existing tested API/service layer.

## Included

- JWT login using an HttpOnly cookie for browser sessions.
- Role-aware sidebar navigation based on existing permissions.
- Store and Financial Year working context.
- Dashboard with current role, stock overview, item count and asset count.
- Current stock page.
- Item master read page.
- Asset register read page.
- API documentation link.
- Logout.

No database schema changes or new business tables are introduced.
Business rules remain in services and authorization layers.

## Security

The web UI does not accept an actor identity from the browser. The login cookie carries the existing JWT. Web routes resolve the current user from that token and perform store visibility checks through the existing AuthorizationService.

In production, configure a random JWT secret of at least 32 bytes and run behind HTTPS.

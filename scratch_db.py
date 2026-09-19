import asyncio
from app.db.session import AsyncSessionLocal
from sqlalchemy import text
async def main():
    async with AsyncSessionLocal() as s:
        res = await s.execute(text("SELECT u.username FROM permissions p JOIN role_permissions rp ON p.id = rp.permission_id JOIN user_roles ur ON rp.role_id = ur.role_id JOIN users u ON ur.user_id = u.id WHERE p.code = 'STOCK_RETURN_VERIFY'"))
        print([r[0] for r in res])
asyncio.run(main())

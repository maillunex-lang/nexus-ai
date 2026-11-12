"""Stage 2 agent capability registry, deliberately no command execution."""
from fastapi import HTTPException, Request
from .identity import current_user

AGENTS = (
    {"id": "director", "name": "AI Director", "specialty": "Планирование и распределение задач"},
    {"id": "developer", "name": "Разработчик", "specialty": "Код и архитектура"},
    {"id": "tester", "name": "Тестировщик", "specialty": "Проверки и качество"},
    {"id": "devops", "name": "DevOps", "specialty": "Инфраструктура и развёртывание"},
    {"id": "artist", "name": "3D / Godot", "specialty": "Игровые ресурсы и графика"},
)


def list_agents(request: Request) -> dict:
    user = current_user(request)
    if not set(user["roles"]).intersection({"owner", "operator", "viewer"}):
        raise HTTPException(403, "Insufficient permissions")
    return {"agents": [{**agent, "status": "planned", "execution_enabled": False} for agent in AGENTS],
            "execution_enabled": False, "message": "Агенты ещё не подключены к исполнителям"}

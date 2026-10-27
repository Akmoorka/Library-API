from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from library.exceptions import ApplicationError
from library.services import loan_create


class Command(BaseCommand):
    help = "Выдать экземпляр читателю (тот же сценарий loan_create, что и в API)."

    def add_arguments(self, parser):
        parser.add_argument("--copy-id", type=int, required=True)
        parser.add_argument("--reader-id", type=int, required=True)
        parser.add_argument("--actor-id", type=int, required=True)

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            actor = User.objects.get(pk=options["actor_id"])
        except User.DoesNotExist:
            raise CommandError(f"Пользователь {options['actor_id']} не найден.")
        # Права, лимиты и все остальные правила проверяет сам сервис.
        try:
            loan = loan_create(
                actor=actor,
                copy_id=options["copy_id"],
                reader_id=options["reader_id"],
            )
        except ApplicationError as exc:
            raise CommandError(f"[{exc.code}] {exc.message}")
        self.stdout.write(
            self.style.SUCCESS(f"Выдача #{loan.pk} создана, вернуть до {loan.due_at}.")
        )

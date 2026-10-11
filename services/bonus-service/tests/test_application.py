import asyncio
from uuid import uuid4

import pytest
from bonus_service.application.service import BonusService
from bonus_service.domain.errors import OperationConflict, OperationNotFound
from bonus_service.domain.models import Account, PrivilegeStatus, PurchaseOperation
from bonus_service.infrastructure.memory import (
    InMemoryRepository,
    InMemoryStore,
    InMemoryUnitOfWork,
)

from tests.conftest import FixedClock


async def test_new_account_and_users_are_isolated(service: BonusService) -> None:
    account = await service.get_account("alice")
    assert account.balance == 0
    assert account.status == PrivilegeStatus.BRONZE
    assert account.history == ()
    await service.apply_purchase("alice", uuid4(), 1500, False)
    assert (await service.get_account("alice")).balance == 150
    assert (await service.get_account("bob")).balance == 0


async def test_purchase_retry_returns_original_snapshot(service: BonusService) -> None:
    ticket = uuid4()
    original, created = await service.apply_purchase("alice", ticket, 1500, False)
    await service.apply_purchase("alice", uuid4(), 1000, False)
    repeated, created_again = await service.apply_purchase("alice", ticket, 1500, False)
    assert created and not created_again
    assert repeated == original
    assert repeated.privilege.balance == 150
    assert (await service.get_account("alice")).balance == 250
    assert len((await service.get_account("alice")).history) == 2


@pytest.mark.parametrize("price,paid_from_balance", [(1600, False), (1500, True)])
async def test_changed_request_conflicts(
    service: BonusService, price: int, paid_from_balance: bool
) -> None:
    ticket = uuid4()
    await service.apply_purchase("alice", ticket, 1500, False)
    with pytest.raises(OperationConflict):
        await service.apply_purchase("alice", ticket, price, paid_from_balance)
    assert (await service.get_account("alice")).balance == 150


async def test_foreign_and_missing_operations_are_hidden(service: BonusService) -> None:
    ticket = uuid4()
    await service.apply_purchase("alice", ticket, 1500, False)
    with pytest.raises(OperationNotFound):
        await service.apply_purchase("bob", ticket, 1500, False)
    for username, uid in [("bob", ticket), ("alice", uuid4())]:
        with pytest.raises(OperationNotFound):
            await service.reverse_purchase(username, uid)
    assert (await service.get_account("alice")).balance == 150


async def test_reversal_retry_returns_current_balance_without_extra_history(
    service: BonusService,
) -> None:
    ticket = uuid4()
    await service.apply_purchase("alice", ticket, 1500, False)
    assert (await service.reverse_purchase("alice", ticket)).balance == 0
    await service.apply_purchase("alice", uuid4(), 1000, False)
    assert (await service.reverse_purchase("alice", ticket)).balance == 100
    assert len((await service.get_account("alice")).history) == 3
    with pytest.raises(OperationConflict):
        await service.apply_purchase("alice", ticket, 1500, False)


async def test_zero_bonus_operation_can_be_reversed_once(service: BonusService) -> None:
    ticket = uuid4()
    payment, _ = await service.apply_purchase("alice", ticket, 1500, True)
    assert payment.paid_by_bonuses == 0
    await service.reverse_purchase("alice", ticket)
    await service.reverse_purchase("alice", ticket)
    assert len((await service.get_account("alice")).history) == 2


async def test_concurrent_duplicate_purchases_apply_once(service: BonusService) -> None:
    ticket = uuid4()
    results = await asyncio.gather(
        *[service.apply_purchase("alice", ticket, 1500, False) for _ in range(20)]
    )
    assert sum(created for _, created in results) == 1
    assert (await service.get_account("alice")).balance == 150
    assert len((await service.get_account("alice")).history) == 1


async def test_concurrent_spending_cannot_overdraw(service: BonusService) -> None:
    await service.apply_purchase("alice", uuid4(), 5000, False)
    results = await asyncio.gather(
        *[service.apply_purchase("alice", uuid4(), 400, True) for _ in range(10)]
    )
    assert sum(result.paid_by_bonuses for result, _ in results) == 500
    assert (await service.get_account("alice")).balance == 0


async def test_concurrent_refunds_apply_once(service: BonusService) -> None:
    await service.apply_purchase("alice", uuid4(), 5000, False)
    ticket = uuid4()
    await service.apply_purchase("alice", ticket, 1500, True)
    await asyncio.gather(*[service.reverse_purchase("alice", ticket) for _ in range(20)])
    account = await service.get_account("alice")
    assert account.balance == 500
    assert len(account.history) == 3


async def test_uncommitted_changes_and_exception_are_rolled_back(store: InMemoryStore) -> None:
    async with store.transaction() as transaction:
        await transaction.repository.save_account(Account("alice", 100))
    assert store.accounts == {}
    with pytest.raises(RuntimeError, match="Failure"):
        async with store.transaction() as transaction:
            await transaction.repository.save_account(Account("alice", 100))
            raise RuntimeError("Failure")
    assert store.accounts == {}
    async with store.transaction() as transaction:
        await transaction.repository.save_account(Account("alice", 50))
        await transaction.commit()
    assert store.accounts["alice"].balance == 50


async def test_stores_are_independent() -> None:
    first, second = InMemoryStore(), InMemoryStore()
    async with first.transaction() as transaction:
        await transaction.repository.save_account(Account("alice", 100))
        await transaction.commit()
    assert second.accounts == {}


async def test_failure_saving_operation_does_not_publish_balance() -> None:
    class FailingRepository(InMemoryRepository):
        async def save_operation(self, operation: PurchaseOperation) -> None:
            raise RuntimeError("Cannot save operation")

    class FailingUnitOfWork(InMemoryUnitOfWork):
        async def __aenter__(self) -> InMemoryUnitOfWork:
            await super().__aenter__()
            self._repository = FailingRepository(
                self.repository.accounts, self.repository.operations
            )
            return self

    store = InMemoryStore()
    service = BonusService(lambda: FailingUnitOfWork(store), FixedClock())
    with pytest.raises(RuntimeError, match="Cannot save operation"):
        await service.apply_purchase("alice", uuid4(), 1500, False)
    assert store.accounts == {}
    assert store.operations == {}
    # A failed transaction must also release its lock for subsequent requests.
    healthy = BonusService(store.transaction, FixedClock())
    assert (await healthy.get_account("alice")).balance == 0

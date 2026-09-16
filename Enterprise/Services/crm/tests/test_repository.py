from datetime import datetime, timezone

from crm_service.models import Customer, CustomerProfile, CustomerSegment
from crm_service.repository import CrmRepository


def test_customer_profile_and_segments_persist_in_service_database(tmp_path):
    database_path = tmp_path / "crm.sqlite3"
    customer = Customer(
        customer_id="customer-1",
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
    )
    profile = CustomerProfile(customer_id=customer.customer_id, city="London")
    segment = CustomerSegment(customer_id=customer.customer_id, segment="early-adopter")

    repository = CrmRepository(database_path)
    repository.save_customer(customer)
    repository.save_profile(profile)
    repository.add_segment(segment)
    repository.close()

    reopened = CrmRepository(database_path)
    assert reopened.get_customer(customer.customer_id) == customer
    assert reopened.get_profile(customer.customer_id) == profile
    assert reopened.get_segments(customer.customer_id) == [segment]
    reopened.close()


def test_upsert_customer_by_email_preserves_identity(tmp_path):
    repository = CrmRepository(tmp_path / "crm.sqlite3")
    first = Customer(first_name="Maya", last_name="Thompson", email="maya@example.test")
    updated = Customer(first_name="Maya", last_name="Revised", email="maya@example.test")

    repository.upsert_customer_by_email(first)
    saved = repository.upsert_customer_by_email(updated)

    assert saved.customer_id == first.customer_id
    stored = repository.list_customers()[0]
    assert stored.customer_id == first.customer_id
    assert stored.last_name == "Revised"
    assert stored.email == "maya@example.test"
    repository.close()


def test_delete_customer_cascades_owned_records(tmp_path):
    database_path = tmp_path / "crm.sqlite3"
    customer = Customer(
        customer_id="customer-2",
        first_name="Grace",
        last_name="Hopper",
        email="grace@example.com",
    )
    repository = CrmRepository(database_path)
    repository.save_customer(customer)
    repository.save_profile(CustomerProfile(customer_id=customer.customer_id))
    repository.add_segment(
        CustomerSegment(
            customer_id=customer.customer_id,
            segment="pioneer",
            effective_from=datetime.now(timezone.utc),
        )
    )

    repository.delete_customer(customer.customer_id)

    assert repository.get_profile(customer.customer_id) is None
    assert repository.get_segments(customer.customer_id) == []
    repository.close()
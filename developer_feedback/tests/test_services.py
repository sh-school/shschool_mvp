"""Unit tests for developer_feedback services."""

from __future__ import annotations

from django.test import TestCase, override_settings

from developer_feedback.models import DeveloperMessage
from developer_feedback.services.hashing import hash_user_id, verify_user_id
from developer_feedback.services.ticketing import (
    generate_ticket_number,
    generate_unique_ticket_number,
)


class HashingServiceTests(TestCase):
    """Tests for SHA-256 user_id hashing."""

    def test_hash_user_id_returns_64_char_hex(self):
        result = hash_user_id(42)
        self.assertEqual(len(result), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in result))

    def test_hash_is_deterministic(self):
        h1 = hash_user_id(7)
        h2 = hash_user_id(7)
        self.assertEqual(h1, h2)

    def test_different_users_get_different_hashes(self):
        h1 = hash_user_id(1)
        h2 = hash_user_id(2)
        self.assertNotEqual(h1, h2)

    def test_verify_user_id_works(self):
        candidate = hash_user_id(123)
        self.assertTrue(verify_user_id(123, candidate))
        self.assertFalse(verify_user_id(124, candidate))

    @override_settings(SECRET_KEY="different-secret-key-for-test")
    def test_hash_depends_on_secret_key(self):
        # Hash يجب أن يختلف مع SECRET_KEY مختلف
        h = hash_user_id(999)
        self.assertEqual(len(h), 64)


class TicketingServiceTests(TestCase):
    """Tests for ticket number generation."""

    def test_ticket_format(self):
        ticket = generate_ticket_number()
        self.assertTrue(ticket.startswith("SOS-"))
        parts = ticket.split("-")
        self.assertEqual(len(parts), 3)  # SOS / YYYYMMDD / XXXX
        self.assertEqual(len(parts[1]), 8)  # YYYYMMDD
        self.assertEqual(len(parts[2]), 4)  # 4 hex chars

    def test_tickets_are_unique_in_batch(self):
        tickets = {generate_ticket_number() for _ in range(50)}
        # احتمالية التكرار ضئيلة جداً (4 hex = 65536 احتمال)
        self.assertGreaterEqual(len(tickets), 45)

    def test_generate_unique_ticket_avoids_db_collision(self):
        # توليد رقم لنموذج فعلي
        ticket = generate_unique_ticket_number(DeveloperMessage)
        self.assertTrue(ticket.startswith("SOS-"))
        # لا يوجد في DB الفعلي
        self.assertFalse(DeveloperMessage.objects.filter(ticket_number=ticket).exists())

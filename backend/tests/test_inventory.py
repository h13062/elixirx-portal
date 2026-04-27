"""Sprint 2 — inventory endpoint tests."""

from conftest import unique_id


class TestProducts:
    def test_get_products(self, client, admin_headers):
        """GET /api/products returns all active products"""
        response = client.get("/api/products", headers=admin_headers)
        assert response.status_code == 200
        products = response.json()
        assert len(products) >= 5, f"Expected at least 5 products, got {len(products)}"
        names = [p["name"] for p in products]
        assert "RX Machine" in names
        assert "RO Machine" in names
        assert "RO Filter" in names

    def test_get_products_as_rep(self, client, rep_headers):
        """Rep can also view products (full transparency)"""
        response = client.get("/api/products", headers=rep_headers)
        assert response.status_code == 200
        assert len(response.json()) >= 5

    def test_create_consumable_product(self, client, admin_headers):
        """Admin can create a new consumable product"""
        sku = unique_id("SKU")
        response = client.post("/api/products", headers=admin_headers, json={
            "name": f"Test Product {sku}", "sku": sku,
            "category": "consumable", "default_price": 25.00, "is_serialized": False
        })
        assert response.status_code == 201, f"Create product failed: {response.json()}"

    def test_create_duplicate_sku_fails(self, client, admin_headers):
        """Duplicate SKU is rejected"""
        sku = unique_id("DUP")
        client.post("/api/products", headers=admin_headers, json={
            "name": f"Product {sku}", "sku": sku,
            "category": "consumable", "default_price": 10.00, "is_serialized": False
        })
        response = client.post("/api/products", headers=admin_headers, json={
            "name": f"Product {sku} copy", "sku": sku,
            "category": "consumable", "default_price": 10.00, "is_serialized": False
        })
        assert response.status_code == 400

    def test_rep_cannot_create_product(self, client, rep_headers):
        """Rep cannot create products"""
        response = client.post("/api/products", headers=rep_headers, json={
            "name": "Should Fail", "sku": "FAIL-001",
            "category": "consumable", "default_price": 10.00, "is_serialized": False
        })
        assert response.status_code == 403

    def test_edit_product(self, client, admin_headers):
        """Admin can edit a product"""
        sku = unique_id("EDIT")
        client.post("/api/products", headers=admin_headers, json={
            "name": f"Product {sku}", "sku": sku,
            "category": "consumable", "default_price": 10.00, "is_serialized": False
        })
        response = client.put(f"/api/products/{sku}", headers=admin_headers, json={
            "description": "Updated description"
        })
        assert response.status_code == 200, f"Edit product failed: {response.json()}"


class TestMachines:
    def _get_rx_product_id(self, client, headers):
        products = client.get("/api/products", headers=headers).json()
        rx = next(p for p in products if p["name"] == "RX Machine")
        return rx["id"]

    def test_register_machine(self, client, admin_headers):
        """Admin can register a new machine"""
        product_id = self._get_rx_product_id(client, admin_headers)
        serial = unique_id("RX")
        response = client.post("/api/machines", headers=admin_headers, json={
            "serial_number": serial, "product_id": product_id,
            "batch_number": "TEST-BATCH", "manufacture_date": "2026-01-15"
        })
        assert response.status_code == 201, f"Register machine failed: {response.json()}"
        assert response.json()["serial_number"] == serial
        assert response.json()["status"] == "available"

    def test_register_duplicate_serial_fails(self, client, admin_headers):
        """Duplicate serial number is rejected"""
        product_id = self._get_rx_product_id(client, admin_headers)
        serial = unique_id("RX")
        client.post("/api/machines", headers=admin_headers, json={
            "serial_number": serial, "product_id": product_id,
            "batch_number": "BATCH", "manufacture_date": "2026-01-15"
        })
        response = client.post("/api/machines", headers=admin_headers, json={
            "serial_number": serial, "product_id": product_id,
            "batch_number": "BATCH", "manufacture_date": "2026-01-15"
        })
        assert response.status_code == 400

    def test_rep_cannot_register_machine(self, client, rep_headers):
        """Rep cannot register machines"""
        response = client.post("/api/machines", headers=rep_headers, json={
            "serial_number": "NOPE-001", "product_id": "doesnt-matter",
            "batch_number": "BATCH", "manufacture_date": "2026-01-15"
        })
        assert response.status_code == 403

    def test_register_machine_with_sku(self, client, admin_headers):
        """Can register machine using product SKU instead of UUID"""
        serial = unique_id("RX")
        response = client.post("/api/machines", headers=admin_headers, json={
            "serial_number": serial, "product_id": "RX-MACHINE",
            "batch_number": "TEST-BATCH", "manufacture_date": "2026-01-15"
        })
        assert response.status_code == 201, f"SKU lookup failed: {response.json()}"

    def test_get_machines(self, client, admin_headers):
        """GET /api/machines returns list"""
        response = client.get("/api/machines", headers=admin_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_filter_by_status(self, client, admin_headers):
        """Filter machines by status"""
        response = client.get("/api/machines?status=available", headers=admin_headers)
        assert response.status_code == 200
        for machine in response.json():
            assert machine["status"] == "available"

    def test_get_machine_by_serial(self, client, admin_headers):
        """Lookup machine by serial number"""
        product_id = self._get_rx_product_id(client, admin_headers)
        serial = unique_id("RX")
        client.post("/api/machines", headers=admin_headers, json={
            "serial_number": serial, "product_id": product_id,
            "batch_number": "BATCH", "manufacture_date": "2026-01-15"
        })
        response = client.get(f"/api/machines/{serial}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["serial_number"] == serial

    def test_machine_not_found(self, client, admin_headers):
        """Nonexistent machine returns 404"""
        response = client.get("/api/machines/NONEXISTENT-999", headers=admin_headers)
        assert response.status_code == 404


class TestConsumableStock:
    def test_get_stock(self, client, admin_headers):
        """GET /api/consumable-stock returns stock levels"""
        response = client.get("/api/consumable-stock", headers=admin_headers)
        assert response.status_code == 200
        assert len(response.json()) >= 3


class TestSupplementFlavors:
    def test_get_flavors(self, client, admin_headers):
        """GET /api/supplement-flavors returns flavors with SKUs"""
        response = client.get("/api/supplement-flavors", headers=admin_headers)
        assert response.status_code == 200
        flavors = response.json()
        assert len(flavors) >= 5

    def test_create_flavor(self, client, admin_headers):
        """Admin can create a new flavor"""
        sku = unique_id("SUPP")
        response = client.post("/api/supplement-flavors", headers=admin_headers, json={
            "name": f"Test Flavor {sku}", "sku": sku
        })
        assert response.status_code == 201, f"Create flavor failed: {response.json()}"

    def test_edit_flavor(self, client, admin_headers):
        """Admin can edit a flavor"""
        sku = unique_id("SUPP")
        created = client.post("/api/supplement-flavors", headers=admin_headers, json={
            "name": f"Flavor {sku}", "sku": sku
        }).json()
        flavor_id = created.get("id")
        if flavor_id:
            response = client.put(
                f"/api/supplement-flavors/{flavor_id}",
                headers=admin_headers,
                json={"name": f"Renamed {sku}"},
            )
            assert response.status_code == 200

    def test_delete_flavor(self, client, admin_headers):
        """Admin can soft-delete a flavor"""
        sku = unique_id("SUPP")
        created = client.post("/api/supplement-flavors", headers=admin_headers, json={
            "name": f"Delete Me {sku}", "sku": sku
        }).json()
        flavor_id = created.get("id")
        if flavor_id:
            response = client.delete(
                f"/api/supplement-flavors/{flavor_id}",
                headers=admin_headers,
            )
            assert response.status_code == 200


class TestConsumableBatches:
    def _get_product_id(self, client, headers, name):
        products = client.get("/api/products", headers=headers).json()
        p = next(p for p in products if p["name"] == name)
        return p["id"]

    def _get_flavor_id(self, client, headers):
        flavors = client.get("/api/supplement-flavors", headers=headers).json()
        return flavors[0]["id"] if flavors else None

    def test_add_filter_batch(self, client, admin_headers):
        """Add a batch of RO Filters"""
        product_id = self._get_product_id(client, admin_headers, "RO Filter")
        batch = unique_id("LOT")
        response = client.post("/api/consumable-batches", headers=admin_headers, json={
            "product_id": product_id, "batch_number": batch,
            "quantity_manufactured": 24, "manufacture_date": "2026-02-15"
        })
        assert response.status_code == 201, f"Add batch failed: {response.json()}"
        data = response.json()
        assert data["quantity_manufactured"] == 24
        assert data["quantity"] == 24
        assert data["status"] == "in_stock"

    def test_supplement_batch_requires_flavor(self, client, admin_headers):
        """Supplement batch without flavor returns 400"""
        product_id = self._get_product_id(client, admin_headers, "Supplement Pack")
        response = client.post("/api/consumable-batches", headers=admin_headers, json={
            "product_id": product_id, "batch_number": "NO-FLAVOR",
            "quantity_manufactured": 30, "manufacture_date": "2026-02-15"
        })
        assert response.status_code == 400

    def test_supplement_batch_with_flavor(self, client, admin_headers):
        """Supplement batch with flavor succeeds"""
        product_id = self._get_product_id(client, admin_headers, "Supplement Pack")
        flavor_id = self._get_flavor_id(client, admin_headers)
        batch = unique_id("LOT")
        response = client.post("/api/consumable-batches", headers=admin_headers, json={
            "product_id": product_id, "batch_number": batch,
            "quantity_manufactured": 30, "manufacture_date": "2026-02-15",
            "flavor_id": flavor_id
        })
        assert response.status_code == 201, f"Supplement batch failed: {response.json()}"

    def test_ship_batch(self, client, admin_headers):
        """Ship partial batch updates quantities and status"""
        product_id = self._get_product_id(client, admin_headers, "RO Filter")
        batch = unique_id("LOT")
        created = client.post("/api/consumable-batches", headers=admin_headers, json={
            "product_id": product_id, "batch_number": batch,
            "quantity_manufactured": 20, "manufacture_date": "2026-02-15"
        }).json()
        response = client.post(
            f"/api/consumable-batches/{created['id']}/ship",
            headers=admin_headers, json={
                "quantity_to_ship": 10, "shipped_date": "2026-02-20",
                "shipped_to": "Heights Nail Spa"
            }
        )
        assert response.status_code == 200, f"Ship failed: {response.json()}"
        data = response.json()
        assert data["quantity"] == 10
        assert data["quantity_shipped"] == 10
        assert data["status"] == "partially_shipped"

    def test_ship_more_than_available_fails(self, client, admin_headers):
        """Cannot ship more than available quantity"""
        product_id = self._get_product_id(client, admin_headers, "RO Filter")
        batch = unique_id("LOT")
        created = client.post("/api/consumable-batches", headers=admin_headers, json={
            "product_id": product_id, "batch_number": batch,
            "quantity_manufactured": 5, "manufacture_date": "2026-02-15"
        }).json()
        response = client.post(
            f"/api/consumable-batches/{created['id']}/ship",
            headers=admin_headers, json={
                "quantity_to_ship": 10, "shipped_date": "2026-02-20",
                "shipped_to": "Test"
            }
        )
        assert response.status_code == 400

    def test_edit_batch(self, client, admin_headers):
        """Admin can edit batch quantity"""
        product_id = self._get_product_id(client, admin_headers, "RO Filter")
        batch = unique_id("LOT")
        created = client.post("/api/consumable-batches", headers=admin_headers, json={
            "product_id": product_id, "batch_number": batch,
            "quantity_manufactured": 10, "manufacture_date": "2026-02-15"
        }).json()
        response = client.put(
            f"/api/consumable-batches/{created['id']}",
            headers=admin_headers, json={"quantity": 8}
        )
        assert response.status_code == 200, f"Edit batch failed: {response.json()}"

    def test_delete_batch(self, client, admin_headers):
        """Admin can delete a batch"""
        product_id = self._get_product_id(client, admin_headers, "RO Filter")
        batch = unique_id("LOT")
        created = client.post("/api/consumable-batches", headers=admin_headers, json={
            "product_id": product_id, "batch_number": batch,
            "quantity_manufactured": 5, "manufacture_date": "2026-02-15"
        }).json()
        response = client.delete(
            f"/api/consumable-batches/{created['id']}",
            headers=admin_headers
        )
        assert response.status_code == 200

    def test_batch_report(self, client, admin_headers):
        """Batch report returns summary data"""
        response = client.get("/api/consumable-batches/report", headers=admin_headers)
        assert response.status_code == 200, f"Report failed: {response.json()}"
        data = response.json()
        assert "summary" in data
        assert "batches" in data

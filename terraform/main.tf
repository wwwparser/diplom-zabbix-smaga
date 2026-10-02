terraform {
  required_version = ">= 1.9.0"
  required_providers { yandex = { source = "yandex-cloud/yandex", version = "= 0.233.0" } }
}
provider "yandex" {
  cloud_id  = var.cloud_id
  folder_id = var.folder_id
  zone      = "ru-central1-a"
}
variable "cloud_id" { type = string }
variable "folder_id" { type = string }
variable "ssh_public_key" { type = string }
variable "admin_cidr" { type = string }
variable "preemptible" { default = false }
locals {
  machines = {
    web-a   = { zone = "ru-central1-a", subnet = "private-a", ip = "10.42.10.10", ram = 2, public = false, role = "web" }
    web-b   = { zone = "ru-central1-b", subnet = "private-b", ip = "10.42.20.10", ram = 2, public = false, role = "web" }
    elastic = { zone = "ru-central1-a", subnet = "private-a", ip = "10.42.10.20", ram = 4, public = false, role = "elastic" }
    zabbix  = { zone = "ru-central1-a", subnet = "public-a", ip = "10.42.1.20", ram = 4, public = true, role = "zabbix" }
    kibana  = { zone = "ru-central1-a", subnet = "public-a", ip = "10.42.1.30", ram = 2, public = true, role = "kibana" }
    bastion = { zone = "ru-central1-a", subnet = "public-a", ip = "10.42.1.10", ram = 2, public = true, role = "bastion" }
  }
  subnets = {
    public-a  = { zone = "ru-central1-a", cidr = "10.42.1.0/24", private = false }
    public-b  = { zone = "ru-central1-b", cidr = "10.42.2.0/24", private = false }
    private-a = { zone = "ru-central1-a", cidr = "10.42.10.0/24", private = true }
    private-b = { zone = "ru-central1-b", cidr = "10.42.20.0/24", private = true }
  }
}
resource "yandex_vpc_network" "lab" { name = "diplom-network" }
resource "yandex_vpc_gateway" "nat" {
  name = "diplom-nat"
  shared_egress_gateway {}
}
resource "yandex_vpc_route_table" "nat" {
  name       = "diplom-private-routes"
  network_id = yandex_vpc_network.lab.id
  static_route {
    destination_prefix = "0.0.0.0/0"
    gateway_id         = yandex_vpc_gateway.nat.id
  }
}
resource "yandex_vpc_subnet" "lab" {
  for_each       = local.subnets
  name           = "diplom-${each.key}"
  zone           = each.value.zone
  network_id     = yandex_vpc_network.lab.id
  v4_cidr_blocks = [each.value.cidr]
  route_table_id = each.value.private ? yandex_vpc_route_table.nat.id : null
}
resource "yandex_vpc_security_group" "common" {
  name       = "diplom-common"
  network_id = yandex_vpc_network.lab.id
  ingress {
    protocol       = "TCP"
    port           = 22
    v4_cidr_blocks = ["10.42.1.10/32"]
    description    = "SSH only from bastion"
  }
  ingress {
    protocol       = "TCP"
    port           = 10050
    v4_cidr_blocks = ["10.42.1.20/32"]
  }
  ingress {
    protocol       = "ICMP"
    v4_cidr_blocks = ["10.42.0.0/16"]
  }
  egress {
    protocol       = "ANY"
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "yandex_vpc_security_group" "role" {
  for_each   = toset(["bastion", "web", "zabbix", "elastic", "kibana", "alb"])
  name       = "diplom-${each.key}"
  network_id = yandex_vpc_network.lab.id
  dynamic "ingress" {
    for_each = each.key == "bastion" ? [22] : each.key == "web" ? [80] : each.key == "zabbix" ? [80, 10051] : each.key == "elastic" ? [9200] : each.key == "kibana" ? [5601] : [80]
    content {
      protocol       = "TCP"
      port           = ingress.value
      v4_cidr_blocks = each.key == "bastion" ? [var.admin_cidr] : each.key == "web" || each.key == "elastic" || ingress.value == 10051 ? ["10.42.0.0/16"] : ["0.0.0.0/0"]
    }
  }
  dynamic "ingress" {
    for_each = each.key == "alb" ? [1] : []
    content {
      protocol          = "TCP"
      port              = 30080
      predefined_target = "loadbalancer_healthchecks"
    }
  }
  egress {
    protocol       = "ANY"
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "yandex_compute_instance" "vm" {
  for_each    = local.machines
  name        = "diplom-${each.key}"
  hostname    = "diplom-${each.key}"
  zone        = each.value.zone
  platform_id = "standard-v3"
  labels      = { project = "netology-diplom", role = each.value.role }
  resources {
    cores         = 2
    core_fraction = 20
    memory        = each.value.ram
  }
  boot_disk {
    initialize_params {
      image_id = "fd84a0ma316h9ddtvdoi"
      size     = 10
      type     = "network-hdd"
    }
  }
  scheduling_policy { preemptible = var.preemptible }
  network_interface {
    subnet_id          = yandex_vpc_subnet.lab[each.value.subnet].id
    ip_address         = each.value.ip
    nat                = each.value.public
    security_group_ids = [yandex_vpc_security_group.common.id, yandex_vpc_security_group.role[each.value.role].id]
  }
  metadata = {
    ssh-keys  = "ubuntu:${var.ssh_public_key}"
    user-data = "#cloud-config\npackage_update: false\nssh_pwauth: false\n"
  }
}
resource "yandex_alb_target_group" "web" {
  name = "diplom-web-targets"
  dynamic "target" {
    for_each = toset(["web-a", "web-b"])
    content {
      subnet_id  = yandex_vpc_subnet.lab[local.machines[target.value].subnet].id
      ip_address = yandex_compute_instance.vm[target.value].network_interface[0].ip_address
    }
  }
}
resource "yandex_alb_backend_group" "web" {
  name = "diplom-web-backends"
  http_backend {
    name             = "nginx"
    port             = 80
    weight           = 1
    target_group_ids = [yandex_alb_target_group.web.id]
    healthcheck {
      timeout             = "2s"
      interval            = "5s"
      healthy_threshold   = 2
      unhealthy_threshold = 2
      http_healthcheck { path = "/" }
    }
  }
}
resource "yandex_alb_http_router" "web" { name = "diplom-router" }
resource "yandex_alb_virtual_host" "web" {
  name           = "diplom-virtual-host"
  http_router_id = yandex_alb_http_router.web.id
  route {
    name = "all"
    http_route {
      http_match {
        path { prefix = "/" }
      }
      http_route_action {
        backend_group_id = yandex_alb_backend_group.web.id
        timeout          = "10s"
      }
    }
  }
}
resource "yandex_alb_load_balancer" "web" {
  name               = "diplom-alb"
  network_id         = yandex_vpc_network.lab.id
  security_group_ids = [yandex_vpc_security_group.role["alb"].id]
  allocation_policy {
    dynamic "location" {
      for_each = toset(["public-a", "public-b"])
      content {
        zone_id   = local.subnets[location.value].zone
        subnet_id = yandex_vpc_subnet.lab[location.value].id
      }
    }
  }
  listener {
    name = "http"
    endpoint {
      address {
        external_ipv4_address {}
      }
      ports = [80]
    }
    http {
      handler { http_router_id = yandex_alb_http_router.web.id }
    }
  }
}
resource "yandex_compute_snapshot_schedule" "daily" {
  name = "diplom-daily-seven-days"
  schedule_policy { expression = "0 2 * * *" }
  retention_period = "168h0m0s"
  snapshot_spec { description = "Daily boot disk snapshot: seven-day retention" }
  disk_ids = [for vm in yandex_compute_instance.vm : vm.boot_disk[0].disk_id]
}
output "machines" {
  value = { for name, vm in yandex_compute_instance.vm : name => { id = vm.id, fqdn = vm.fqdn, ip = vm.network_interface[0].ip_address, public_ip = vm.network_interface[0].nat_ip_address, disk_id = vm.boot_disk[0].disk_id } }
}
output "alb_ip" { value = yandex_alb_load_balancer.web.listener[0].endpoint[0].address[0].external_ipv4_address[0].address }
output "snapshot_schedule_id" { value = yandex_compute_snapshot_schedule.daily.id }

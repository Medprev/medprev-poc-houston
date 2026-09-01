from houston.fingerprint import (
    error_tracking_fingerprint,
    k8s_fingerprint,
    monitor_fingerprint,
)


def test_error_tracking_fingerprint_is_stable():
    assert error_tracking_fingerprint("114e7438-e897-11ef-83c4-da7ad0900002") == (
        "et-114e7438-e897-11ef-83c4-da7ad0900002"
    )


def test_monitor_fingerprint_without_group():
    assert monitor_fingerprint(167097893) == "mon-167097893"


def test_monitor_fingerprint_with_group():
    assert monitor_fingerprint(167097893, "host:web-1") == "mon-167097893-host:web-1"


def test_k8s_fingerprint_strips_replicaset_and_pod_hash_suffix():
    a = k8s_fingerprint("prod-eks", "BackOff", "medprev-rest-api-7f9b8d6c9d-x2k7p")
    b = k8s_fingerprint("prod-eks", "BackOff", "medprev-rest-api-58a1c2f4a1-m9q3z")
    assert a == b == "k8s-prod-eks-BackOff-medprev-rest-api"


def test_k8s_fingerprint_is_a_pure_function():
    args = ("prod-eks", "OOMKilled", "worker-6b7d9f8c5-abcde")
    assert k8s_fingerprint(*args) == k8s_fingerprint(*args)

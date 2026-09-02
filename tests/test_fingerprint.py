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


def test_k8s_fingerprint_is_cluster_reason_namespace():
    assert k8s_fingerprint("prod-eks", "BackOff", "medprev-rest-api") == (
        "k8s-prod-eks-BackOff-medprev-rest-api"
    )


def test_namespaces_ending_in_a_number_stay_distinct():
    """Regression test: the old pod-hash strip ran `-[0-9]+$` over what is
    now a namespace, so `medprev-web-app-2` collapsed onto
    `medprev-web-app` and dedup-by-file-existence then suppressed the
    second namespace permanently (ADR-0019)."""
    assert k8s_fingerprint("prod-eks", "BackOff", "medprev-web-app-2") != (
        k8s_fingerprint("prod-eks", "BackOff", "medprev-web-app")
    )


def test_k8s_fingerprint_is_a_pure_function():
    args = ("prod-eks", "OOMKilled", "medprev-rest-api")
    assert k8s_fingerprint(*args) == k8s_fingerprint(*args)

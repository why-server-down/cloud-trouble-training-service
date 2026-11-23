import pytest

from app.services.command_validator import CommandValidator

NAMESPACE = "user-test123"


@pytest.fixture
def validator():
    return CommandValidator()


class TestAllowedCommands:
    def test_get_pods(self, validator):
        result = validator.validate_command("kubectl get pods", NAMESPACE)
        assert result.is_valid
        assert f"-n {NAMESPACE}" in result.command

    def test_describe_pod(self, validator):
        result = validator.validate_command("kubectl describe pod my-pod", NAMESPACE)
        assert result.is_valid

    def test_logs(self, validator):
        result = validator.validate_command("kubectl logs my-pod", NAMESPACE)
        assert result.is_valid

    def test_apply_blocked(self, validator):
        # apply 는 임의 매니페스트를 올릴 수 있어 허용 목록에서 뺐다.
        result = validator.validate_command("kubectl apply -f deployment.yaml", NAMESPACE)
        assert not result.is_valid
        assert "not allowed" in result.error

    def test_top_blocked(self, validator):
        # top 은 어떤 미션에도 쓰지 않고 metrics-server 에 의존한다.
        result = validator.validate_command("kubectl top pods", NAMESPACE)
        assert not result.is_valid

    def test_run_overrides_blocked(self, validator):
        # --overrides 로 특권 Pod 를 만들던 경로를 막는다.
        result = validator.validate_command(
            "kubectl run pwn --image=alpine --overrides={}", NAMESPACE
        )
        assert not result.is_valid

    def test_server_flag_blocked(self, validator):
        # 다른 apiserver 지정·신원 변경 전역 옵션은 거절한다.
        for cmd in (
            "kubectl get pods --server=https://evil",
            "kubectl get pods --as=system:admin",
            "kubectl get pods --kubeconfig=/tmp/x",
        ):
            result = validator.validate_command(cmd, NAMESPACE)
            assert not result.is_valid, cmd

    def test_explain(self, validator):
        result = validator.validate_command("kubectl explain pod", NAMESPACE)
        assert result.is_valid

    def test_set_image(self, validator):
        result = validator.validate_command(
            "kubectl set image deployment/nginx nginx=nginx:latest", NAMESPACE
        )
        assert result.is_valid
        assert f"-n {NAMESPACE}" in result.command

    def test_patch(self, validator):
        result = validator.validate_command(
            'kubectl patch deployment/nginx -p "{\\"spec\\": {}}"', NAMESPACE
        )
        assert result.is_valid
        assert f"-n {NAMESPACE}" in result.command


class TestBlockedCommands:
    def test_non_kubectl(self, validator):
        result = validator.validate_command("rm -rf /", NAMESPACE)
        assert not result.is_valid
        assert "Only kubectl" in result.error

    def test_invalid_subcommand(self, validator):
        result = validator.validate_command("kubectl create secret", NAMESPACE)
        assert not result.is_valid
        assert "not allowed" in result.error

    def test_empty_kubectl(self, validator):
        result = validator.validate_command("kubectl", NAMESPACE)
        assert not result.is_valid

    def test_pipe(self, validator):
        result = validator.validate_command("kubectl get pods | grep error", NAMESPACE)
        assert not result.is_valid
        assert "forbidden" in result.error

    def test_redirect(self, validator):
        result = validator.validate_command("kubectl get pods > output.txt", NAMESPACE)
        assert not result.is_valid

    def test_command_chaining(self, validator):
        result = validator.validate_command("kubectl get pods && rm -rf /", NAMESPACE)
        assert not result.is_valid

    def test_semicolon(self, validator):
        result = validator.validate_command("kubectl get pods; ls", NAMESPACE)
        assert not result.is_valid

    def test_command_substitution_backtick(self, validator):
        result = validator.validate_command("kubectl get pods `whoami`", NAMESPACE)
        assert not result.is_valid

    def test_command_substitution_dollar(self, validator):
        result = validator.validate_command("kubectl get pods $(whoami)", NAMESPACE)
        assert not result.is_valid


class TestNamespaceInjection:
    def test_namespace_injected(self, validator):
        result = validator.validate_command("kubectl get pods", NAMESPACE)
        assert result.is_valid
        assert f"-n {NAMESPACE}" in result.command

    def test_existing_namespace_allowed(self, validator):
        result = validator.validate_command(f"kubectl get pods -n {NAMESPACE}", NAMESPACE)
        assert result.is_valid

    def test_wrong_namespace_blocked(self, validator):
        result = validator.validate_command("kubectl get pods -n kube-system", NAMESPACE)
        assert not result.is_valid
        assert "Access denied" in result.error

    def test_wrong_namespace_long_flag(self, validator):
        result = validator.validate_command("kubectl get pods --namespace=default", NAMESPACE)
        assert not result.is_valid
        assert "Access denied" in result.error


class TestDeleteConfirmation:
    def test_delete_requires_confirmation(self, validator):
        result = validator.validate_command("kubectl delete pod my-pod", NAMESPACE)
        assert not result.is_valid
        assert result.requires_confirmation

    def test_delete_confirmed(self, validator):
        result = validator.validate_delete("kubectl delete pod my-pod", NAMESPACE, confirmed=True)
        assert result.is_valid

    def test_delete_not_confirmed(self, validator):
        result = validator.validate_delete("kubectl delete pod my-pod", NAMESPACE, confirmed=False)
        assert not result.is_valid
        assert result.requires_confirmation


class TestCreateRestrictions:
    """kubectl create 는 훈련 복구에 필요한 리소스만, 이름까지 갖춘 형태로 허용한다."""

    def test_create_secret_without_type_blocked(self, validator):
        result = validator.validate_command("kubectl create secret", NAMESPACE)
        assert not result.is_valid
        assert "not allowed" in result.error

    def test_create_secret_generic_allowed(self, validator):
        result = validator.validate_command(
            "kubectl create secret generic app-secret --from-literal=key=value", NAMESPACE
        )
        assert result.is_valid
        assert f"-n {NAMESPACE}" in result.command

    def test_create_secret_without_name_blocked(self, validator):
        result = validator.validate_command(
            "kubectl create secret generic --from-literal=key=value", NAMESPACE
        )
        assert not result.is_valid
        assert "not allowed" in result.error

    def test_create_configmap_allowed(self, validator):
        result = validator.validate_command("kubectl create configmap app-config", NAMESPACE)
        assert result.is_valid

    def test_create_deployment_blocked(self, validator):
        result = validator.validate_command(
            "kubectl create deployment nginx --image=nginx", NAMESPACE
        )
        assert not result.is_valid
        assert "not allowed" in result.error

    def test_create_without_resource_blocked(self, validator):
        result = validator.validate_command("kubectl create", NAMESPACE)
        assert not result.is_valid
        assert "not allowed" in result.error

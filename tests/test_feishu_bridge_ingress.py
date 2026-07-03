from blastogene.feishu_bridge_ingress import BridgeMessage, FeishuBridgeIngress, IngressPolicy


def test_ingress_silently_ignores_unmentioned_group_message():
    policy = IngressPolicy(owner_id="ou_owner", allowed_chats=frozenset({"oc_group"}))
    msg = BridgeMessage("group", "oc_group", "ou_user", "hello", mentioned_bot=False)
    assert FeishuBridgeIngress().decide(msg, policy) == "ignore"


def test_ingress_requires_invite_for_unknown_group_mentions():
    policy = IngressPolicy(owner_id="ou_owner")
    msg = BridgeMessage("group", "oc_unknown", "ou_user", "@bot help", mentioned_bot=True)
    assert FeishuBridgeIngress().decide(msg, policy) == "invite-required"

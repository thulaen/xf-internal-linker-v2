"""Characterization tests for the streamd Go sidecar.
Tests the gRPC API as a black box.
"""
import os
import uuid
import pytest
import grpc

try:
    from apps.realtime._streamd_pb2.api_pb2 import (
        PublishRequest,
        SubscribeRequest,
        HealthRequest,
        ManageRequest,
        AckOffsetCommand,
        GetConsumerOffsetCommand,
        TopicStatsCommand,
    )
    from apps.realtime._streamd_pb2 import api_pb2_grpc
    STUBS_AVAILABLE = True
except ImportError:
    STUBS_AVAILABLE = False

SOCKET_PATH = os.environ.get("XF_STREAMD_SOCKET", "/var/run/xf/streamd.sock")

@pytest.fixture(scope="module")
def grpc_channel():
    if not STUBS_AVAILABLE:
        pytest.skip("streamd protobuf stubs not generated yet")
    if not os.path.exists(SOCKET_PATH):
        pytest.skip("streamd socket not found")

    target = f"unix://{SOCKET_PATH}"
    channel = grpc.insecure_channel(target)
    try:
        grpc.channel_ready_future(channel).result(timeout=2.0)
    except grpc.FutureTimeoutError:
        pytest.skip(f"streamd socket at {SOCKET_PATH} not responding")
        
    yield channel
    channel.close()

@pytest.fixture(scope="module")
def stub(grpc_channel):
    return api_pb2_grpc.StreamdStub(grpc_channel)

def test_health_check(stub):
    """Test health check RPC returns SERVING."""
    resp = stub.Health(HealthRequest(), timeout=2.0)
    # status 1 corresponds to SERVING in ServingStatus
    assert resp.status == 1

def test_publish_and_subscribe(stub):
    """Test publishing and replaying events via Subscribe RPC."""
    topic = f"char-test-{uuid.uuid4().hex}"
    
    resp1 = stub.Publish(PublishRequest(topic=topic, payload=b"msg1"), timeout=2.0)
    assert resp1.offset > 0
    
    resp2 = stub.Publish(PublishRequest(topic=topic, payload=b"msg2"), timeout=2.0)
    assert resp2.offset == resp1.offset + 1

    call = stub.Subscribe(SubscribeRequest(topic=topic, from_offset=resp1.offset, consumer_id="char-consumer"))
    
    ev1 = next(call)
    assert ev1.offset == resp1.offset
    assert ev1.payload == b"msg1"
    assert ev1.topic == topic

    ev2 = next(call)
    assert ev2.offset == resp2.offset
    assert ev2.payload == b"msg2"

    call.cancel()

def test_manage_topic_stats(stub):
    """Test retrieving topic stats via Manage RPC."""
    topic = f"char-test-stats-{uuid.uuid4().hex}"
    stub.Publish(PublishRequest(topic=topic, payload=b"msg"), timeout=2.0)
    
    def req_generator():
        yield ManageRequest(topic_stats=TopicStatsCommand(topic=topic))
    
    call = stub.Manage(req_generator(), timeout=5.0)
    resp = next(call)
    
    assert resp.HasField("topic_stats")
    stats = resp.topic_stats
    assert stats.topic == topic
    # Topic introspection is not yet exposed by the streamd broker,
    # so these currently return 0.
    assert stats.next_offset == 0
    assert stats.buffered_event_count == 0
    assert stats.consumer_count == 0
    
    call.cancel()

def test_manage_ack_and_get_offset(stub):
    """Test acking and fetching a consumer offset via Manage RPC."""
    topic = f"char-test-ack-{uuid.uuid4().hex}"
    consumer = f"consumer-{uuid.uuid4().hex}"
    
    pub_resp = stub.Publish(PublishRequest(topic=topic, payload=b"msg"), timeout=2.0)
    
    def req_generator():
        yield ManageRequest(ack=AckOffsetCommand(topic=topic, consumer_id=consumer, offset=pub_resp.offset))
        yield ManageRequest(get_offset=GetConsumerOffsetCommand(topic=topic, consumer_id=consumer))
        
    call = stub.Manage(req_generator(), timeout=5.0)
    
    resp1 = next(call)
    assert resp1.HasField("ack")
    assert resp1.ack.accepted is True
    
    resp2 = next(call)
    assert resp2.HasField("get_offset")
    assert resp2.get_offset.present is True
    assert resp2.get_offset.offset == pub_resp.offset
    
    call.cancel()

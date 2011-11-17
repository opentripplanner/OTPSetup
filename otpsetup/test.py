from kombu import BrokerConnection, Exchange, Queue

media_exchange = Exchange("amq.direct", type="direct", durable=True)
video_queue = Queue("video", exchange=media_exchange, routing_key="video")
video_queue = Queue("video", exchange=media_exchange, routing_key="transload")

def process_media(body, message):
    print body
    message.ack()

# connections
with BrokerConnection("amqp://kombu:lxcJZooKna.wg@localhost//kombu") as conn:

    # produce
    with conn.Producer(exchange=media_exchange,
                       serializer="json", routing_key="video") as producer:
#        producer.publish({"name": "/tmp/lolcat1.avi", "size": 1301013})
#        producer.publish({"name": "/tmp/lolcat2.avi", "size": 1301013})
        pass

    # consume
    with conn.Consumer(video_queue, callbacks=[process_media]) as consumer:
        # Process messages and handle events on all channels
        print "drain"
        conn.drain_events()


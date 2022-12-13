# Kafka/Zookeeper metrics
Based off the steps from: https://strimzi.io/docs/operators/latest/deploying.html#proc-metrics-kafka-deploy-options-str

The docs reference this folder for how to setup metrics: https://github.com/strimzi/strimzi-kafka-operator/tree/0.32.0/examples/metrics

kubectl -n sma get kafka cluster -o yaml > kafka_cluster_backup.yaml

## Kafka

```yaml
ncn-m001:/mnt/developer/sjostrand # cat kafka-metrics.yaml
---
kind: ConfigMap
apiVersion: v1 
metadata:
  name: kafka-metrics
  labels:
    app: strimzi
data:
  kafka-metrics-config.yml: |
    # See https://github.com/prometheus/jmx_exporter for more info about JMX Prometheus Exporter metrics
    lowercaseOutputName: true
    rules:
    # Special cases and very specific rules
    - pattern: kafka.server<type=(.+), name=(.+), clientId=(.+), topic=(.+), partition=(.*)><>Value
      name: kafka_server_$1_$2
      type: GAUGE
      labels:
       clientId: "$3"
       topic: "$4"
       partition: "$5"
    - pattern: kafka.server<type=(.+), name=(.+), clientId=(.+), brokerHost=(.+), brokerPort=(.+)><>Value
      name: kafka_server_$1_$2
      type: GAUGE
      labels:
       clientId: "$3"
       broker: "$4:$5"
    - pattern: kafka.server<type=(.+), cipher=(.+), protocol=(.+), listener=(.+), networkProcessor=(.+)><>connections
      name: kafka_server_$1_connections_tls_info
      type: GAUGE
      labels:
        cipher: "$2"
        protocol: "$3"
        listener: "$4"
        networkProcessor: "$5"
    - pattern: kafka.server<type=(.+), clientSoftwareName=(.+), clientSoftwareVersion=(.+), listener=(.+), networkProcessor=(.+)><>connections
      name: kafka_server_$1_connections_software
      type: GAUGE
      labels:
        clientSoftwareName: "$2"
        clientSoftwareVersion: "$3"
        listener: "$4"
        networkProcessor: "$5"
    - pattern: "kafka.server<type=(.+), listener=(.+), networkProcessor=(.+)><>(.+):"
      name: kafka_server_$1_$4
      type: GAUGE
      labels:
       listener: "$2"
       networkProcessor: "$3"
    - pattern: kafka.server<type=(.+), listener=(.+), networkProcessor=(.+)><>(.+)
      name: kafka_server_$1_$4
      type: GAUGE
      labels:
       listener: "$2"
       networkProcessor: "$3"
    # Some percent metrics use MeanRate attribute
    # Ex) kafka.server<type=(KafkaRequestHandlerPool), name=(RequestHandlerAvgIdlePercent)><>MeanRate
    - pattern: kafka.(\w+)<type=(.+), name=(.+)Percent\w*><>MeanRate
      name: kafka_$1_$2_$3_percent
      type: GAUGE
    # Generic gauges for percents
    - pattern: kafka.(\w+)<type=(.+), name=(.+)Percent\w*><>Value
      name: kafka_$1_$2_$3_percent
      type: GAUGE
    - pattern: kafka.(\w+)<type=(.+), name=(.+)Percent\w*, (.+)=(.+)><>Value
      name: kafka_$1_$2_$3_percent
      type: GAUGE
      labels:
        "$4": "$5"
    # Generic per-second counters with 0-2 key/value pairs
    - pattern: kafka.(\w+)<type=(.+), name=(.+)PerSec\w*, (.+)=(.+), (.+)=(.+)><>Count
      name: kafka_$1_$2_$3_total
      type: COUNTER
      labels:
        "$4": "$5"
        "$6": "$7"
    - pattern: kafka.(\w+)<type=(.+), name=(.+)PerSec\w*, (.+)=(.+)><>Count
      name: kafka_$1_$2_$3_total
      type: COUNTER
      labels:
        "$4": "$5"
    - pattern: kafka.(\w+)<type=(.+), name=(.+)PerSec\w*><>Count
      name: kafka_$1_$2_$3_total
      type: COUNTER
    # Generic gauges with 0-2 key/value pairs
    - pattern: kafka.(\w+)<type=(.+), name=(.+), (.+)=(.+), (.+)=(.+)><>Value
      name: kafka_$1_$2_$3
      type: GAUGE
      labels:
        "$4": "$5"
        "$6": "$7"
    - pattern: kafka.(\w+)<type=(.+), name=(.+), (.+)=(.+)><>Value
      name: kafka_$1_$2_$3
      type: GAUGE
      labels:
        "$4": "$5"
    - pattern: kafka.(\w+)<type=(.+), name=(.+)><>Value
      name: kafka_$1_$2_$3
      type: GAUGE
    # Emulate Prometheus 'Summary' metrics for the exported 'Histogram's.
    # Note that these are missing the '_sum' metric!
    - pattern: kafka.(\w+)<type=(.+), name=(.+), (.+)=(.+), (.+)=(.+)><>Count
      name: kafka_$1_$2_$3_count
      type: COUNTER
      labels:
        "$4": "$5"
        "$6": "$7"
    - pattern: kafka.(\w+)<type=(.+), name=(.+), (.+)=(.*), (.+)=(.+)><>(\d+)thPercentile
      name: kafka_$1_$2_$3
      type: GAUGE
      labels:
        "$4": "$5"
        "$6": "$7"
        quantile: "0.$8"
    - pattern: kafka.(\w+)<type=(.+), name=(.+), (.+)=(.+)><>Count
      name: kafka_$1_$2_$3_count
      type: COUNTER
      labels:
        "$4": "$5"
    - pattern: kafka.(\w+)<type=(.+), name=(.+), (.+)=(.*)><>(\d+)thPercentile
      name: kafka_$1_$2_$3
      type: GAUGE
      labels:
        "$4": "$5"
        quantile: "0.$6"
    - pattern: kafka.(\w+)<type=(.+), name=(.+)><>Count
      name: kafka_$1_$2_$3_count
      type: COUNTER
    - pattern: kafka.(\w+)<type=(.+), name=(.+)><>(\d+)thPercentile
      name: kafka_$1_$2_$3
      type: GAUGE
      labels:
        quantile: "0.$4"
  zookeeper-metrics-config.yml: |
    # See https://github.com/prometheus/jmx_exporter for more info about JMX Prometheus Exporter metrics
    lowercaseOutputName: true
    rules:
    # replicated Zookeeper
    - pattern: "org.apache.ZooKeeperService<name0=ReplicatedServer_id(\\d+)><>(\\w+)"
      name: "zookeeper_$2"
      type: GAUGE
    - pattern: "org.apache.ZooKeeperService<name0=ReplicatedServer_id(\\d+), name1=replica.(\\d+)><>(\\w+)"
      name: "zookeeper_$3"
      type: GAUGE
      labels:
        replicaId: "$2"
    - pattern: "org.apache.ZooKeeperService<name0=ReplicatedServer_id(\\d+), name1=replica.(\\d+), name2=(\\w+)><>(Packets\\w+)"
      name: "zookeeper_$4"
      type: COUNTER
      labels:
        replicaId: "$2"
        memberType: "$3"
    - pattern: "org.apache.ZooKeeperService<name0=ReplicatedServer_id(\\d+), name1=replica.(\\d+), name2=(\\w+)><>(\\w+)"
      name: "zookeeper_$4"
      type: GAUGE
      labels:
        replicaId: "$2"
        memberType: "$3"
    - pattern: "org.apache.ZooKeeperService<name0=ReplicatedServer_id(\\d+), name1=replica.(\\d+), name2=(\\w+), name3=(\\w+)><>(\\w+)"
      name: "zookeeper_$4_$5"
      type: GAUGE
      labels:
        replicaId: "$2"
        memberType: "$3"
```

Edit kafka custom resource

```
kubectl -n sma apply -f kafka-metrics.yaml
```

Here are the changes to enable kafka metrics
```
[22-11-17 17:19:04] root@ncn-m001: /home/sjostrand/kafka # diff kafka_cluster_backup.yaml kafka_cluster_with_metrics.yaml
8c8
<   generation: 4
---
>   generation: 5
13c13
<   resourceVersion: "679800968"
---
>   resourceVersion: "688612543"
35a36,41
>     metricsConfig:
>       type: jmxPrometheusExporter
>       valueFrom:
>         configMapKeyRef:
>           key: kafka-metrics-config.yml
>           name: kafka-metrics
48a55,57
>   kafkaExporter:
>     groupRegex: .*
>     topicRegex: .*
```

Add pod monitor

```yaml
ncn-m001:/mnt/developer/sjostrand # cat strimzi-pod-monitor.yaml
---
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: sma-kafka-resources-metrics
  namespace: sysmgmt-health
  labels:
    app: strimzi
    release: cray-sysmgmt-health
spec:
  selector:
    matchExpressions:
      - key: "strimzi.io/kind"
        operator: In
        values: ["Kafka", "KafkaConnect", "KafkaMirrorMaker", "KafkaMirrorMaker2"]
  namespaceSelector:
    matchNames:
      - sma
  podMetricsEndpoints:
  - path: /metrics
    port: tcp-prometheus
    relabelings:
    - separator: ;
      regex: __meta_kubernetes_pod_label_(strimzi_io_.+)
      replacement: $1
      action: labelmap
    - sourceLabels: [__meta_kubernetes_namespace]
      separator: ;
      regex: (.*)
      targetLabel: namespace
      replacement: $1
      action: replace
    - sourceLabels: [__meta_kubernetes_pod_name]
      separator: ;
      regex: (.*)
      targetLabel: kubernetes_pod_name
      replacement: $1
      action: replace
    - sourceLabels: [__meta_kubernetes_pod_node_name]
      separator: ;
      regex: (.*)
      targetLabel: node_name
      replacement: $1
      action: replace
    - sourceLabels: [__meta_kubernetes_pod_host_ip]
      separator: ;
      regex: (.*)
      targetLabel: node_ip
      replacement: $1
      action: replace
```

```
kubectl apply -f strimzi-pod-monitor.yaml
```




## Zookeeper 
I added zookeeper metrics after the fact from the kafka metrics above. 

```
  zookeeper:
    config:
      tickTime: "5000"
    jvmOptions:
      -XX:
        UseG1GC: true
      -Xms: 4096m
      -Xmx: 4096m
    metricsConfig:
      type: jmxPrometheusExporter
      valueFrom:
        configMapKeyRef:
          key: zookeeper-metrics-config.yml
          name: kafka-metrics
```


Full kafka custom resource:
```
[22-11-18 22:18:57] root@ncn-m001: /home/sjostrand # kubectl -n sma get kafka cluster  -o yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  annotations:
    meta.helm.sh/release-name: sma-zk-kafka
    meta.helm.sh/release-namespace: sma
  creationTimestamp: "2021-04-19T02:37:47Z"
  generation: 11
  labels:
    app.kubernetes.io/managed-by: Helm
  name: cluster
  namespace: sma
  resourceVersion: "690122585"
  uid: 3fdb24d8-21eb-4116-bd13-7eb55e3a7522
spec:
  entityOperator:
    topicOperator: {}
    userOperator: {}
  kafka:
    config:
      auto.create.topics.enable: "false"
      broker.id: 1
      delete.topic.enable: "true"
      log.message.format.version: "2.1"
      offsets.topic.replication.factor: 3
      transaction.state.log.min.isr: 2
      transaction.state.log.replication.factor: 3
    jvmOptions:
      -XX:
        G1HeapRegionSize: 16M
        InitiatingHeapOccupancyPercent: 35
        MaxGCPauseMillis: 20
        MaxMetaspaceFreeRatio: 80
        MetaspaceSize: 96m
        MinMetaspaceFreeRatio: 50
        UseG1GC: true
      -Xms: 6g
      -Xmx: 6g
    listeners:
    - name: plain
      port: 9092
      tls: false
      type: internal
    metricsConfig:
      type: jmxPrometheusExporter
      valueFrom:
        configMapKeyRef:
          key: kafka-metrics-config.yml
          name: kafka-metrics
    replicas: 3
    resources:
      limits:
        cpu: 12
        memory: 64Gi
      requests:
        cpu: 6
        memory: 8Gi
    storage:
      deleteClaim: false
      size: 16957Gi
      type: persistent-claim
    version: 2.8.1
  kafkaExporter:
    groupRegex: .*
    topicRegex: .*
  zookeeper:
    config:
      tickTime: "5000"
    jvmOptions:
      -XX:
        UseG1GC: true
      -Xms: 4096m
      -Xmx: 4096m
    metricsConfig:
      type: jmxPrometheusExporter
      valueFrom:
        configMapKeyRef:
          key: zookeeper-metrics-config.yml
          name: kafka-metrics
    replicas: 3
    resources:
      limits:
        cpu: 4
        memory: 8Gi
      requests:
        cpu: 2
        memory: 8Gi
    storage:
      deleteClaim: false
      size: 1Gi
      type: persistent-claim
status:
  clusterId: 7iD0rrF6Ru-xp2DfY9HvQA
  conditions:
  - lastTransitionTime: "2022-11-18T21:02:02.570721Z"
    message: log.message.format.version does not match the Kafka cluster version,
      which suggests that an upgrade is incomplete.
    reason: KafkaLogMessageFormatVersion
    status: "True"
    type: Warning
  - lastTransitionTime: "2022-11-18T21:02:02.570839Z"
    message: default.replication.factor option is not configured. It defaults to 1
      which does not guarantee reliability and availability. You should configure
      this option in .spec.kafka.config.
    reason: KafkaDefaultReplicationFactor
    status: "True"
    type: Warning
  - lastTransitionTime: "2022-11-18T21:02:02.570887Z"
    message: min.insync.replicas option is not configured. It defaults to 1 which
      does not guarantee reliability and availability. You should configure this option
      in .spec.kafka.config.
    reason: KafkaMinInsyncReplicas
    status: "True"
    type: Warning
  - lastTransitionTime: "2022-11-18T21:02:03.239Z"
    status: "True"
    type: Ready
  listeners:
  - addresses:
    - host: cluster-kafka-bootstrap.sma.svc
      port: 9092
    bootstrapServers: cluster-kafka-bootstrap.sma.svc:9092
    type: plain
  observedGeneration: 11
```

## Grafana
I loaded the following dashboards into grafana:
* https://github.com/strimzi/strimzi-kafka-operator/blob/0.27.1/examples/metrics/grafana-dashboards/strimzi-zookeeper.json
* https://github.com/strimzi/strimzi-kafka-operator/blob/0.27.1/examples/metrics/grafana-dashboards/strimzi-kafka.json
* https://github.com/strimzi/strimzi-kafka-operator/blob/0.27.1/examples/metrics/grafana-dashboards/strimzi-kafka-exporter.json
  * @Jeff this one shows consumer lag :smile:
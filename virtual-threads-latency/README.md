# Virtual threads p95 demo

Two independent Maven projects. There is no parent POM.

| Project | Role | Port |
| --- | --- | --- |
| `delay-stub` | `GET /delay` blocks for 60 ms plus up to 15 ms of jitter | 8081 |
| `order-api` | `GET /orders/{id}` waits on that stub, then returns `{id, status}` | 8080 |

`order-api` defaults to a Tomcat pool of 40 platform threads. The `virtual` profile sets `spring.threads.virtual.enabled=true`. The load client holds 200 concurrent callers so the platform pool queues and virtual threads do not.

## Layout

```
delay-stub/src/main/java/demo/stub/
  DelayStubApplication.java
  controller/DelayController.java
  model/DelayResponse.java

order-api/src/main/java/demo/order/
  OrderApiApplication.java
  controller/OrderController.java
  config/DownstreamClientConfig.java
  config/DownstreamProperties.java
  model/OrderResponse.java

load/
  orders.py      # concurrent caller; prints p50, p95, p99
  compare.sh     # runs orders.py against both modes
```

## What you need

- JDK 21 or newer (`java -version`)
- Maven 3.9+
- Python 3 (stdlib only; no pip packages)
- `curl`

## 1. Build

From this directory (`virtual-threads-latency`):

```bash
mvn -f delay-stub/pom.xml package -DskipTests
mvn -f order-api/pom.xml package -DskipTests
```

## 2. Start the stub

Leave this process running in its own terminal:

```bash
java -jar delay-stub/target/delay-stub-1.0.0.jar
```

If `java` is not on your `PATH`, set `JAVA_HOME` first. On this machine that JDK is Homebrew OpenJDK:

```bash
export JAVA_HOME=/opt/homebrew/Cellar/openjdk/27/libexec/openjdk.jdk/Contents/Home
export PATH="$JAVA_HOME/bin:$PATH"
```

Check the stub:

```bash
curl -s "http://127.0.0.1:8081/delay?ms=1"
```

You should see `{"sleptMs":1}`.

## 3. Compare platform threads and virtual threads

In a second terminal, from `virtual-threads-latency`:

```bash
sh load/compare.sh
```

The script does this for each mode:

1. Starts `order-api` (no profile, then `--spring.profiles.active=virtual`).
2. Waits until `http://127.0.0.1:8080/actuator/health` returns.
3. Warms up with 40 callers for 5 seconds.
4. Measures with 200 callers for 45 seconds via `load/orders.py`.
5. Stops that JVM before starting the next one.

Logs and the raw percentile lines are written to `load/results/`. The script ends with both p95 numbers and the percent drop.

A previous run on this machine looked like this (your numbers will move a little):

| Mode | Throughput | p50 | p95 |
| --- | --- | --- | --- |
| Platform threads | 569 rps | 345 ms | 374 ms |
| Virtual threads | 2,682 rps | 71 ms | 103 ms |

That was about 72% lower p95, with zero errors. The gap is larger than 20% because 200 callers fully saturate a pool of 40 threads. To shrink the gap, rerun the Python client yourself with fewer callers (step 4).

## 4. Run one mode yourself

Platform pool of 40:

```bash
java -jar order-api/target/order-api-1.0.0.jar
```

Virtual threads:

```bash
java -jar order-api/target/order-api-1.0.0.jar --spring.profiles.active=virtual
```

Smoke check:

```bash
curl -s "http://127.0.0.1:8080/orders/1"
```

You should see `{"id":"1","status":"FILLED"}` in roughly 60–80 ms when the server is idle.

Load only the process that is currently on port 8080:

```bash
python3 load/orders.py --vus 200 --duration 45
```

Useful knobs:

- `--vus` concurrent callers (default 200)
- `--duration` seconds to hold the load (default 45)
- `--timeout` socket timeout in seconds (default 5)

Example for a milder queue, closer to a 20% gap:

```bash
python3 load/orders.py --vus 80 --duration 45
```

Stop the order API with Ctrl-C before starting the other profile. Only one process can bind port 8080.

// Controlled SuT fixture for the JUnit adapter Gradle path. Deterministic,
// isolated, no `novetest` imports. Same one-line bug in `subtract` as the
// Maven sibling fixture so the same failure surfaces with predictable shape.
//
// No `gradlew` wrapper is committed in this slice — the integration test
// runs `gradle test --no-daemon` against system Gradle, skip-gated on
// `shutil.which("gradle") is None`. See `scripts/dev-host-setup.md §5` for
// the Gradle install path. A future hardening cycle can add the wrapper
// (it just needs to be regenerated via `gradle wrapper` on an equipped
// host).

plugins {
    `java-library`
    jacoco
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    // Gradle 9 dropped the implicit injection of `junit-platform-launcher`
    // into `testRuntimeClasspath` that Gradle 7.6/8.x added when
    // `useJUnitPlatform()` was declared. Declaring the dependency
    // explicitly is the JUnit project's recommended post-9 pattern and
    // is backwards-compatible across Gradle 7.6/8.x/9.x. Added per
    // hotfix #2 2026-06-04 after Manual Test surfaced the Gradle 9
    // incompatibility on the equipped host.
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports {
        xml.required.set(true)
        html.required.set(false)
    }
}

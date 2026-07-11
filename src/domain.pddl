(define (domain smart-hospital-room)
  (:requirements :strips :typing)

  (:types
    room patient light fan door buzzer red-led
  )

  (:predicates
    ;; Static placement facts
    (light-in ?l - light ?r - room)
    (fan-in ?f - fan ?r - room)
    (door-in ?d - door ?r - room)
    (buzzer-in ?b - buzzer ?r - room)
    (red-led-in ?led - red-led ?r - room)
    (patient-in ?p - patient ?r - room)

    ;; Light closed state:
    ;; off    = light-not-on + light-not-dim
    ;; dim    = light-on     + light-dim
    ;; bright = light-on     + light-not-dim
    (light-on ?l - light)
    (light-not-on ?l - light)
    (light-dim ?l - light)
    (light-not-dim ?l - light)

    ;; Fan closed state:
    ;; off    = not-on + not-medium + not-high
    ;; low    = on     + not-medium + not-high
    ;; medium = on     + medium     + not-high
    ;; high   = on     + not-medium + high
    (fan-on ?f - fan)
    (fan-not-on ?f - fan)
    (fan-medium ?f - fan)
    (fan-not-medium ?f - fan)
    (fan-high ?f - fan)
    (fan-not-high ?f - fan)

    ;; Door: exactly one fact is true
    (door-locked ?d - door)
    (door-unlocked ?d - door)

    ;; Buzzer closed state:
    ;; off  = not-on + not-high
    ;; low  = on     + not-high
    ;; high = on     + high
    (buzzer-on ?b - buzzer)
    (buzzer-not-on ?b - buzzer)
    (buzzer-high ?b - buzzer)
    (buzzer-not-high ?b - buzzer)

    ;; Red LED closed state:
    ;; off   = not-on + not-blinking
    ;; blink = on     + blinking
    (red-led-on ?led - red-led)
    (red-led-not-on ?led - red-led)
    (red-led-blinking ?led - red-led)
    (red-led-not-blinking ?led - red-led)

    ;; Observed binary sensor facts; the hardware side supplies one fact
    ;; from each positive/negative pair in every PDDL problem.
    (sos-pressed ?r - room)
    (sos-not-pressed ?r - room)
    (air-hazardous ?r - room)
    (air-not-hazardous ?r - room)
    (temperature-unsafe ?r - room)
    (temperature-not-unsafe ?r - room)
    (temperature-hot ?r - room)
    (temperature-not-hot ?r - room)
    (humidity-high ?r - room)
    (humidity-not-high ?r - room)
    (room-dark ?r - room)
    (room-not-dark ?r - room)
    (patient-on-bed ?p - patient)
    (patient-not-on-bed ?p - patient)
    (motion-recent ?p - patient)
    (motion-not-recent ?p - patient)
    (spo2-low ?p - patient)
    (spo2-not-low ?p - patient)
    (pulse-abnormal ?p - patient)
    (pulse-not-abnormal ?p - patient)
    (out-of-bed-alert-due ?p - patient)
    (out-of-bed-alert-not-due ?p - patient)

    ;; These are multi-valued labels, not binary complements.
    ;; Exactly one room state and one patient state are supplied per problem.
    (room-normal ?r - room)
    (room-hazardous ?r - room)
    (room-emergency ?r - room)
    (patient-awake ?p - patient)
    (patient-resting ?p - patient)
    (patient-out-of-bed ?p - patient)
    (patient-distress ?p - patient)
  )

  ;; ---------------- Light ----------------
  (:action set-light-off
    :parameters (?l - light ?r - room)
    :precondition (light-in ?l ?r)
    :effect (and
      (light-not-on ?l)
      (light-not-dim ?l)
      (not (light-on ?l))
      (not (light-dim ?l))
    )
  )

  (:action set-light-medium
    :parameters (?l - light ?r - room)
    :precondition (light-in ?l ?r)
    :effect (and
      (light-on ?l)
      (light-dim ?l)
      (not (light-not-on ?l))
      (not (light-not-dim ?l))
    )
  )

  (:action set-light-max
    :parameters (?l - light ?r - room)
    :precondition (light-in ?l ?r)
    :effect (and
      (light-on ?l)
      (light-not-dim ?l)
      (not (light-not-on ?l))
      (not (light-dim ?l))
    )
  )

  ;; ---------------- Fan ----------------
  (:action set-fan-off
    :parameters (?f - fan ?r - room)
    :precondition (fan-in ?f ?r)
    :effect (and
      (fan-not-on ?f)
      (fan-not-medium ?f)
      (fan-not-high ?f)
      (not (fan-on ?f))
      (not (fan-medium ?f))
      (not (fan-high ?f))
    )
  )

  (:action set-fan-low
    :parameters (?f - fan ?r - room)
    :precondition (fan-in ?f ?r)
    :effect (and
      (fan-on ?f)
      (fan-not-medium ?f)
      (fan-not-high ?f)
      (not (fan-not-on ?f))
      (not (fan-medium ?f))
      (not (fan-high ?f))
    )
  )

  (:action set-fan-medium
    :parameters (?f - fan ?r - room)
    :precondition (fan-in ?f ?r)
    :effect (and
      (fan-on ?f)
      (fan-medium ?f)
      (fan-not-high ?f)
      (not (fan-not-on ?f))
      (not (fan-not-medium ?f))
      (not (fan-high ?f))
    )
  )

  (:action set-fan-high
    :parameters (?f - fan ?r - room)
    :precondition (fan-in ?f ?r)
    :effect (and
      (fan-on ?f)
      (fan-not-medium ?f)
      (fan-high ?f)
      (not (fan-not-on ?f))
      (not (fan-medium ?f))
      (not (fan-not-high ?f))
    )
  )

  ;; ---------------- Door ----------------
  (:action lock-door
    :parameters (?d - door ?r - room)
    :precondition (door-in ?d ?r)
    :effect (and
      (door-locked ?d)
      (not (door-unlocked ?d))
    )
  )

  (:action unlock-door
    :parameters (?d - door ?r - room)
    :precondition (door-in ?d ?r)
    :effect (and
      (door-unlocked ?d)
      (not (door-locked ?d))
    )
  )

  ;; ---------------- Buzzer ----------------
  (:action set-buzzer-off
    :parameters (?b - buzzer ?r - room)
    :precondition (buzzer-in ?b ?r)
    :effect (and
      (buzzer-not-on ?b)
      (buzzer-not-high ?b)
      (not (buzzer-on ?b))
      (not (buzzer-high ?b))
    )
  )

  (:action set-buzzer-low
    :parameters (?b - buzzer ?r - room)
    :precondition (buzzer-in ?b ?r)
    :effect (and
      (buzzer-on ?b)
      (buzzer-not-high ?b)
      (not (buzzer-not-on ?b))
      (not (buzzer-high ?b))
    )
  )

  (:action set-buzzer-high
    :parameters (?b - buzzer ?r - room)
    :precondition (buzzer-in ?b ?r)
    :effect (and
      (buzzer-on ?b)
      (buzzer-high ?b)
      (not (buzzer-not-on ?b))
      (not (buzzer-not-high ?b))
    )
  )

  ;; ---------------- Red LED ----------------
  (:action set-red-led-off
    :parameters (?led - red-led ?r - room)
    :precondition (red-led-in ?led ?r)
    :effect (and
      (red-led-not-on ?led)
      (red-led-not-blinking ?led)
      (not (red-led-on ?led))
      (not (red-led-blinking ?led))
    )
  )

  ;; Solid ON (critical states): lit but not blinking.
  (:action set-red-led-on
    :parameters (?led - red-led ?r - room)
    :precondition (red-led-in ?led ?r)
    :effect (and
      (red-led-on ?led)
      (red-led-not-blinking ?led)
      (not (red-led-not-on ?led))
      (not (red-led-blinking ?led))
    )
  )

  (:action set-red-led-blink
    :parameters (?led - red-led ?r - room)
    :precondition (red-led-in ?led ?r)
    :effect (and
      (red-led-on ?led)
      (red-led-blinking ?led)
      (not (red-led-not-on ?led))
      (not (red-led-not-blinking ?led))
    )
  )
)

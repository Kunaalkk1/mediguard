(define (domain smart-hospital-room)
  (:requirements :strips :typing)

  (:types
    room light fan door buzzer
  )

  (:predicates
    ;; Object locations
    (light-in ?l - light ?r - room)
    (fan-in ?f - fan ?r - room)
    (door-in ?d - door ?r - room)
    (buzzer-in ?b - buzzer ?r - room)

    ;; Light state
    (light-off ?l - light)
    (light-medium ?l - light)
    (light-max ?l - light)

    ;; Fan state
    (fan-low ?f - fan)
    (fan-medium ?f - fan)
    (fan-high ?f - fan)

    ;; Door state
    (door-locked ?d - door)
    (door-unlocked ?d - door)

    ;; Buzzer state
    (buzzer-off ?b - buzzer)
    (buzzer-low ?b - buzzer)
    (buzzer-high ?b - buzzer)
  )

  (:action set-light-off
    :parameters (?l - light ?r - room)
    :precondition (light-in ?l ?r)
    :effect (and
      (light-off ?l)
      (not (light-medium ?l))
      (not (light-max ?l))
    )
  )

  (:action set-light-medium
    :parameters (?l - light ?r - room)
    :precondition (light-in ?l ?r)
    :effect (and
      (light-medium ?l)
      (not (light-off ?l))
      (not (light-max ?l))
    )
  )

  (:action set-light-max
    :parameters (?l - light ?r - room)
    :precondition (light-in ?l ?r)
    :effect (and
      (light-max ?l)
      (not (light-off ?l))
      (not (light-medium ?l))
    )
  )

  (:action set-fan-low
    :parameters (?f - fan ?r - room)
    :precondition (fan-in ?f ?r)
    :effect (and
      (fan-low ?f)
      (not (fan-medium ?f))
      (not (fan-high ?f))
    )
  )

  (:action set-fan-medium
    :parameters (?f - fan ?r - room)
    :precondition (fan-in ?f ?r)
    :effect (and
      (fan-medium ?f)
      (not (fan-low ?f))
      (not (fan-high ?f))
    )
  )

  (:action set-fan-high
    :parameters (?f - fan ?r - room)
    :precondition (fan-in ?f ?r)
    :effect (and
      (fan-high ?f)
      (not (fan-low ?f))
      (not (fan-medium ?f))
    )
  )

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

  (:action set-buzzer-off
    :parameters (?b - buzzer ?r - room)
    :precondition (buzzer-in ?b ?r)
    :effect (and
      (buzzer-off ?b)
      (not (buzzer-low ?b))
      (not (buzzer-high ?b))
    )
  )

  (:action set-buzzer-low
    :parameters (?b - buzzer ?r - room)
    :precondition (buzzer-in ?b ?r)
    :effect (and
      (buzzer-low ?b)
      (not (buzzer-off ?b))
      (not (buzzer-high ?b))
    )
  )

  (:action set-buzzer-high
    :parameters (?b - buzzer ?r - room)
    :precondition (buzzer-in ?b ?r)
    :effect (and
      (buzzer-high ?b)
      (not (buzzer-off ?b))
      (not (buzzer-low ?b))
    )
  )
)

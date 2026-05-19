from .logger import EvaluationLogger
from .csv_writer import write_csv

def build_context(state, action):

    # TODO: ajustar a tu engine real
    return {
        "enemy_distance": 3,
        "terrain": "forest",
        "hp": 3
    }


def run_evaluation(env, model, opponent, num_episodes=200):

    logger = EvaluationLogger("exp_001")

    for ep in range(num_episodes):

        state = env.reset()
        done = False
        turn = 0

        while not done:

            # -------- RL DECIDE --------
            action, hrl_payload = model.act(state)


            # -------- CONTEXT --------
            context = build_context(state, action)

            logger.log_decision(
                episode_id=ep,
                turn=turn,
                unit_id=action.unit_id,
                hrl_payload=hrl_payload,
                context=context
            )

            # -------- STEP --------
            next_state, result, done, info = env.step(action)

            # -------- OUTCOME --------
            logger.log_outcome(
                episode_id=ep,
                turn=turn,
                unit_id=action.unit_id,
                action=action.type,
                result=result
            )

            state = next_state
            turn += 1

        # -------- EPISODE SUMMARY --------
        summary = env.get_summary()

        logger.log_episode(ep, summary)

    # -------- SAVE CSV --------
    write_csv("episodes.csv", logger.episodes)
    write_csv("decisions.csv", logger.decisions)
    write_csv("outcomes.csv", logger.outcomes)
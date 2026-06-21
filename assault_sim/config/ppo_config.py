class PPOConfig:
    RL_SIDE = "US"
    SCENARIO = "phase01_seq001_initial_contact"
    SEED = 42

    TOTAL_UPDATES = 4000

    # PPO
    ROLLOUT_STEPS = 160        # ✅ más contexto (mejor decisiones)
    PPO_EPOCHS = 3             # ✅ aprende mejor de cada batch
    CLIP_EPS = 0.1
    SEQ_LEN = 8
    MINIBATCH_SEQS = 64
    MAX_KL = 0.08

    # Discounting
    GAMMA = 0.99
    LAMBDA = 0.95

    # Loss
    VALUE_COEF = 0.5
    ENTROPY_COEF = 0.07        # v4: bump exploration to break policy plateau

    # Parallelism
    NUM_ENVS = 22
    BATCH_ROLLOUTS = 4

    # Optimizer
    LR = 8e-5
    EVAL_INTERVAL = 200
    EVAL_EPISODES = 12
    EVAL_MIN_IMPROVEMENT = 0.01
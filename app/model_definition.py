import torch
import torch.nn as nn

# --- Configuration (must match training for architecture) ---
# These are default values; they will be passed during instantiation in main.py
# INPUT_SIZE = 115 (passed during instantiation)
# HIDDEN_SIZE_1 = 256 (passed during instantiation)
# HIDDEN_SIZE_2 = 128 (passed during instantiation)
# OUTPUT_SIZE = 1 (passed during instantiation)
# DROPOUT_RATE = 0.4 (passed during instantiation)

class MLPDetector(nn.Module):
    def __init__(self, input_size, hidden_size_1, hidden_size_2, output_size, dropout_rate):
        super(MLPDetector, self).__init__()
        # Using nn.Sequential for a slightly cleaner look
        self.fc_stack = nn.Sequential(
            nn.Linear(input_size, hidden_size_1),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_size_1, hidden_size_2),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_size_2, output_size)
        )

    def forward(self, x):
        x = self.fc_stack(x)
        return x
import torch
from typing import Dict, Tuple, List
from dataclasses import dataclass

@dataclass
class TensorConfig:
    pad_token_id: int
    max_prompt_length: int
    max_obs_length: int
    max_start_length: int

class TensorHelper:
    def __init__(self, config: TensorConfig):
        self.config = config

    def cut_to_effective_len(self, tensor_dict: Dict[str, torch.Tensor], 
                            keys: List[str], cut_left: bool = True) -> Dict[str, torch.Tensor]:
        """Cut tensors to their effective length based on attention mask."""
        effective_len = tensor_dict['attention_mask'].sum(dim=1).max()
        result = tensor_dict.copy()
        
        for key in keys:
            if cut_left:
                result[key] = tensor_dict[key][:, -effective_len:]
            else:
                result[key] = tensor_dict[key][:, :effective_len]
        return result

    def convert_pad_structure(self, tensor: torch.Tensor, pad_to_left: bool = True) -> Tuple[torch.Tensor, torch.Tensor]:
        """Convert padding structure and return sorted tensor with indices."""
        mask = tensor != self.config.pad_token_id if pad_to_left else tensor == self.config.pad_token_id
        sorted_indices = mask.to(torch.int64).argsort(dim=1, stable=True)
        return tensor.gather(1, sorted_indices), sorted_indices

    def create_attention_mask(self, input_ids: torch.Tensor) -> torch.Tensor:
        """Create attention mask from input ids."""
        return torch.where(input_ids != self.config.pad_token_id, 1, 0)

    def create_position_ids(self, attention_mask: torch.Tensor) -> torch.Tensor:
        """Create position ids from attention mask."""
        return (torch.cumsum(attention_mask, dim=1) - 1) * attention_mask

    def concatenate_with_padding(self, tensors: List[torch.Tensor], 
                               pad_to_left: bool = True) -> torch.Tensor:
        """Concatenate tensors and handle padding."""
        concatenated = torch.cat(tensors, dim=1)
        padded_tensor, _ = self.convert_pad_structure(concatenated, pad_to_left)
        return padded_tensor

    def _example_level_pad(self, responses: torch.Tensor, 
                          responses_str: List[str], 
                          active_mask: torch.Tensor) -> Tuple[torch.Tensor, List[str]]:
        """
        Pad responses for non-active examples with pad tokens.
        """
        assert active_mask.sum() == responses.shape[0]
        # Create masked responses tensor
        batch_size = active_mask.shape[0]
        seq_len = responses.shape[1]
        padded_responses = torch.full(
            (batch_size, seq_len), self.config.pad_token_id,
            dtype=responses.dtype, device=responses.device
        )
        padded_responses[active_mask] = responses
        
        # Create masked response strings
        padded_responses_str = [""] * batch_size
        
        s = 0
        for i, is_active in enumerate(active_mask):
            if is_active:
                padded_responses_str[i] = responses_str[s]
                s += 1
                
        return padded_responses, padded_responses_str

    def _example_level_pad_tensor(self, x: torch.Tensor, active_mask: torch.Tensor, pad_value=0.0) -> torch.Tensor:
        assert active_mask.sum() == x.shape[0]
        batch_size = active_mask.shape[0]
        seq_len = x.shape[1]
        padded_x = torch.full(
            (batch_size, seq_len), pad_value,
            dtype=x.dtype, device=x.device
        )
        padded_x[active_mask] = x
        return padded_x

    def pad_and_stack(self, tensor_list: List[torch.Tensor], pad_to_left=True, pad_value=None):
        """
        对不同长度的张量列表进行统一 padding 并堆叠。

        Args:
            tensor_list (List[torch.Tensor]): 一个包含 1D 张量的列表。
            pad_to_left (bool): 如果为 True，则在左侧填充；否则在右侧填充。

        Returns:
            torch.Tensor: 一个形状为 (n, m) 的张量。
        """
        # Step 1: 找到目标长度
        max_length = max([tensor.size(0) for tensor in tensor_list])

        if pad_value == None:
            pad_value = self.config.pad_token_id
        
        # Step 2: 按照左侧或右侧进行 padding
        if pad_to_left:
            padded_tensors = [
                torch.cat([torch.full((max_length - tensor.size(0),), pad_value, dtype=tensor.dtype, device=tensor.device), tensor])
                for tensor in tensor_list
            ]
        else:
            padded_tensors = [
                torch.cat([tensor, torch.full((max_length - tensor.size(0),), pad_value,  dtype=tensor.dtype, device=tensor.device)])
                for tensor in tensor_list
            ]
        
        # Step 3: 堆叠张量
        stacked_tensor = torch.stack(padded_tensors, dim=0)
        
        return stacked_tensor
        